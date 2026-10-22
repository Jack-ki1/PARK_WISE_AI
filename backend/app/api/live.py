"""Live View API: camera/stream CRUD, calibration snapshots, events and the frame WebSocket."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..database import SessionLocal, get_db
from ..models import Stream, VideoJob
from ..schemas import StreamCreate, StreamPatch, StreamSpacesSave
from ..security import actor_name, authenticate, current_user, rate_limit, validate_external_url
from ..services import activity, billing, settings_store
from ..services.live_stream import load_spaces, manager, save_snapshot, snapshot_for

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
# The frame WebSocket authenticates via ?key= when auth is required (browsers cannot
# send headers on a WebSocket handshake), so it lives on a router without header auth.
ws_router = APIRouter(prefix="/api")


def _stream_out(db: Session, stream: Stream) -> dict:
    session = manager.get(stream.id)
    spaces = load_spaces(stream)
    job = db.get(VideoJob, stream.video_id) if stream.video_id else None
    return {
        "id": stream.id,
        "name": stream.name,
        "kind": stream.kind,
        "url": stream.url,
        "video_id": stream.video_id,
        "video_name": job.original_name if job else None,
        "enabled": stream.enabled,
        "status": session.status if session and session.alive else stream.status,
        "last_error": session.last_error if session and session.alive else stream.last_error,
        "target_fps": stream.target_fps,
        "running": bool(session and session.alive),
        "subscriber_count": session.subscribers if session else stream.subscriber_count,
        "frames_delivered": session.frames_delivered if session else stream.frames_delivered,
        "last_frame_at": stream.last_frame_at.isoformat() if stream.last_frame_at else None,
        "lat": stream.lat,
        "lon": stream.lon,
        "spaces": spaces,
        "space_count": len(spaces),
        "snapshot_url": f"/api/streams/{stream.id}/snapshot" if stream.snapshot_path else None,
        "created_at": stream.created_at.isoformat() if stream.created_at else None,
    }


def _load_stream(db: Session, stream_id: str) -> Stream:
    stream = db.get(Stream, stream_id)
    if stream is None:
        raise HTTPException(status_code=404, detail="Stream not found")
    return stream


@router.get("/streams")
def list_streams(db: Session = Depends(get_db)) -> dict:
    rows = db.query(Stream).order_by(Stream.created_at.desc()).all()
    return {"items": [_stream_out(db, row) for row in rows]}


@router.post("/streams", status_code=201, dependencies=[Depends(rate_limit)])
def create_stream(
    payload: StreamCreate, user=Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    billing.check_can_add_stream(db)
    url = None
    if payload.kind == "url":
        if not payload.url:
            raise HTTPException(status_code=422, detail="url is required for kind='url'")
        try:
            url = validate_external_url(payload.url)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid source URL: {exc}") from None
    else:
        if not payload.video_id or db.get(VideoJob, payload.video_id) is None:
            raise HTTPException(status_code=422, detail="video_id must reference an existing upload")
    stream = Stream(
        id=str(uuid.uuid4()),
        name=payload.name,
        kind=payload.kind,
        url=url,
        video_id=payload.video_id if payload.kind == "video" else None,
        target_fps=payload.target_fps,
        lat=payload.lat,
        lon=payload.lon,
        created_at=datetime.now(timezone.utc),
    )
    db.add(stream)
    db.commit()
    activity.record(db, actor_name(user), "stream.created", "stream", stream.id, stream.name)
    return _stream_out(db, stream)


@router.get("/streams/{stream_id}")
def get_stream(stream_id: str, db: Session = Depends(get_db)) -> dict:
    return _stream_out(db, _load_stream(db, stream_id))


@router.patch("/streams/{stream_id}", dependencies=[Depends(rate_limit)])
def patch_stream(
    stream_id: str, payload: StreamPatch, user=Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    stream = _load_stream(db, stream_id)
    data = payload.model_dump(exclude_unset=True)
    if "url" in data and data["url"]:
        try:
            data["url"] = validate_external_url(data["url"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=f"Invalid source URL: {exc}") from None
    if "video_id" in data and data["video_id"]:
        if db.get(VideoJob, data["video_id"]) is None:
            raise HTTPException(status_code=422, detail="video_id must reference an existing upload")
    for key, value in data.items():
        setattr(stream, key, value)
    db.commit()
    manager.stop(stream_id)  # source changed: next connect starts fresh
    activity.record(db, actor_name(user), "stream.updated", "stream", stream.id, ", ".join(data))
    return _stream_out(db, stream)


@router.delete("/streams/{stream_id}", status_code=204, dependencies=[Depends(rate_limit)])
def delete_stream(stream_id: str, user=Depends(current_user), db: Session = Depends(get_db)) -> Response:
    stream = _load_stream(db, stream_id)
    manager.stop(stream_id)
    activity.record(db, actor_name(user), "stream.deleted", "stream", stream.id, stream.name)
    db.delete(stream)
    db.commit()
    return Response(status_code=204)


@router.put("/streams/{stream_id}/spaces", dependencies=[Depends(rate_limit)])
def save_stream_spaces(
    stream_id: str, payload: StreamSpacesSave, user=Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    stream = _load_stream(db, stream_id)
    stream.spaces_json = json.dumps([space.model_dump() for space in payload.spaces])
    db.commit()
    activity.record(db, actor_name(user), "stream.calibrated", "stream", stream.id, f"{len(payload.spaces)} bays")
    return _stream_out(db, stream)


@router.post("/streams/{stream_id}/snapshot", dependencies=[Depends(rate_limit)])
def capture_snapshot(stream_id: str, db: Session = Depends(get_db)) -> dict:
    stream = _load_stream(db, stream_id)
    inference = settings_store.inference_config(db)
    try:
        jpeg = snapshot_for(stream, load_spaces(stream), inference)
    except Exception as exc:  # pragma: no cover - cv2/source specific
        raise HTTPException(status_code=502, detail=f"Could not capture frame: {exc}") from None
    if not jpeg:
        raise HTTPException(status_code=502, detail="Source did not deliver a frame")
    path = save_snapshot(stream_id, jpeg)
    stream.snapshot_path = path
    db.commit()
    return {"snapshot_url": f"/api/streams/{stream_id}/snapshot", "bytes": len(jpeg)}


@router.get("/streams/{stream_id}/snapshot")
def get_snapshot(stream_id: str, db: Session = Depends(get_db)) -> FileResponse:
    stream = _load_stream(db, stream_id)
    if not stream.snapshot_path:
        raise HTTPException(status_code=404, detail="No snapshot captured yet")
    path = env_settings.data_path / "streams" / f"{stream_id}_calib.jpg"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Snapshot file is missing")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/streams/{stream_id}/events")
def stream_events(stream_id: str, db: Session = Depends(get_db)) -> dict:
    _load_stream(db, stream_id)
    session = manager.get(stream_id)
    return {"items": session.recent_events(30) if session else []}


@router.post("/streams/{stream_id}/start", dependencies=[Depends(rate_limit)])
def start_stream(stream_id: str, db: Session = Depends(get_db)) -> dict:
    stream = _load_stream(db, stream_id)
    if not stream.enabled:
        raise HTTPException(status_code=409, detail="Stream is disabled")
    inference = settings_store.inference_config(db)
    try:
        session = manager.start(stream, load_spaces(stream), inference)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return {"status": session.status, "running": session.alive}


@router.post("/streams/{stream_id}/stop", dependencies=[Depends(rate_limit)])
def stop_stream(stream_id: str, db: Session = Depends(get_db)) -> dict:
    _load_stream(db, stream_id)
    stopped = manager.stop(stream_id)
    return {"status": "idle", "stopped": stopped}


@ws_router.websocket("/ws/streams/{stream_id}")
async def stream_frames(websocket: WebSocket, stream_id: str) -> None:
    """Push annotated frames (base64 JPEG) + occupancy/event payloads while connected."""
    if env_settings.auth_required:
        token = websocket.query_params.get("key")
        db_probe = SessionLocal()
        try:
            if authenticate(db_probe, token) is None:
                await websocket.close(code=4401, reason="A valid API key is required")
                return
        finally:
            db_probe.close()

    db = SessionLocal()
    try:
        stream = db.get(Stream, stream_id)
        if stream is None:
            await websocket.close(code=1008, reason="Stream not found")
            return
        if not stream.enabled:
            await websocket.close(code=1008, reason="Stream is disabled")
            return
        spaces = load_spaces(stream)
        inference = settings_store.inference_config(db)
    finally:
        db.close()

    await websocket.accept()
    try:
        session = manager.get(stream_id)
        if session is None or not session.alive:
            session = manager.start(stream, spaces, inference)
    except ValueError as exc:
        await websocket.send_text(json.dumps({"type": "error", "detail": str(exc)}))
        await websocket.close(code=1011, reason=str(exc))
        return

    session.add_subscriber()
    await websocket.send_text(
        json.dumps({"type": "status", "status": session.status, "stream_id": stream_id})
    )

    disconnected = asyncio.Event()

    async def watch_disconnect() -> None:
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
        except WebSocketDisconnect:
            pass
        except Exception:  # pragma: no cover - socket torn down
            pass
        finally:
            disconnected.set()

    watcher = asyncio.create_task(watch_disconnect())
    last_seq = -1
    last_ping = 0.0
    try:
        while not disconnected.is_set():
            seq, jpeg, payload = session.snapshot()
            if seq != last_seq and jpeg:
                last_seq = seq
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "frame",
                            "seq": seq,
                            "jpeg": base64.b64encode(jpeg).decode("ascii"),
                            **payload,
                        }
                    )
                )
            now = asyncio.get_event_loop().time()
            if now - last_ping > 2.0:
                last_ping = now
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "status",
                            "status": session.status,
                            "error": session.last_error,
                            "subscribers": session.subscribers,
                        }
                    )
                )
            if session.status == "error" and not session.alive:
                await websocket.send_text(
                    json.dumps({"type": "error", "detail": session.last_error or "Stream failed"})
                )
                break
            try:
                await asyncio.wait_for(disconnected.wait(), timeout=0.12)
            except (asyncio.TimeoutError, TimeoutError):
                pass
    except (WebSocketDisconnect, RuntimeError, ConnectionError):
        pass
    finally:
        watcher.cancel()
        if session.remove_subscriber() <= 0:
            await asyncio.to_thread(manager.stop_if_idle, stream_id)
