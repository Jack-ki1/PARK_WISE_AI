from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal, get_db
from ..models import DetectionSample, OccupancySample, ParkingSpace, VideoJob
from ..schemas import DashboardSummary, DetectionPoint, OccupancyPoint, OccupancySeries, PublicSourceList, SourceOut, SpaceCreate, SpaceOut, VideoJobOut
from ..security import current_user, rate_limit
from ..services import activity, billing, settings_store
from ..services.public_sources import PUBLIC_SOURCES, list_public_sources
from ..services.video_pipeline import inspect_video, process_video_job

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
ALLOWED_EXTENSIONS = {".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm"}


def _video_out(job: VideoJob, db: Session) -> VideoJobOut:
    return VideoJobOut(
        id=job.id,
        original_name=job.original_name,
        source_type=job.source_type,
        source_id=job.source_id,
        source_title=job.source_title,
        source_page=job.source_page,
        status=job.status,
        progress_percent=job.progress_percent,
        current_frame=job.current_frame,
        processed_frames=job.processed_frames,
        width=job.width,
        height=job.height,
        fps=job.fps,
        source_frame_count=job.source_frame_count,
        duration_seconds=job.duration_seconds,
        max_vehicle_count=job.max_vehicle_count,
        avg_confidence=job.avg_confidence,
        error_message=job.error_message,
        model_name=job.model_name,
        created_at=job.created_at,
        completed_at=job.completed_at,
        preview_url=f"/api/videos/{job.id}/preview" if job.preview_path and Path(job.preview_path).exists() else None,
        original_url=f"/api/videos/{job.id}/original" if Path(job.file_path).exists() else None,
        annotated_url=f"/api/videos/{job.id}/annotated" if job.processed_video_path and Path(job.processed_video_path).exists() else None,
        configured_spaces=db.query(ParkingSpace).filter(ParkingSpace.video_id == job.id).count(),
    )


def _load_job(video_id: str, db: Session) -> VideoJob:
    job = db.get(VideoJob, video_id)
    if not job:
        raise HTTPException(status_code=404, detail="Video job not found")
    return job


def _make_job(path: Path, original_name: str, db: Session, *, source_type: str = "upload", source_id: str | None = None, source_title: str | None = None, source_page: str | None = None) -> VideoJob:
    job_id = str(uuid.uuid4())
    preview = settings.data_path / "previews" / f"{job_id}.jpg"
    try:
        meta = inspect_video(path, preview)
    except Exception:
        path.unlink(missing_ok=True)
        preview.unlink(missing_ok=True)
        raise
    if meta["duration"] and meta["duration"] > settings.max_video_seconds:
        path.unlink(missing_ok=True)
        preview.unlink(missing_ok=True)
        raise HTTPException(status_code=413, detail=f"Video duration exceeds {settings.max_video_seconds} seconds")
    job = VideoJob(
        id=job_id,
        original_name=original_name[:255],
        file_path=str(path.resolve()),
        source_type=source_type,
        source_id=source_id,
        source_title=source_title,
        source_page=source_page,
        status="uploaded",
        width=meta["width"],
        height=meta["height"],
        fps=meta["fps"],
        source_frame_count=meta["frame_count"],
        duration_seconds=meta["duration"],
        preview_path=str(preview.resolve()),
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


@router.get("/health")
def health():
    return {"status": "ok", "service": "parkwise-ai-api", "time": datetime.now(timezone.utc).isoformat()}


@router.get("/config/public")
def public_config(db: Session = Depends(get_db)):
    """Expose operational, non-secret settings so the dashboard reports true config."""
    effective = settings_store.inference_config(db)
    return {
        **effective,
        "max_upload_mb": settings.max_upload_mb,
        "max_video_seconds": settings.max_video_seconds,
        "public_source_fetch_enabled": bool(settings_store.get(db, "public_sources_enabled")),
        "auth_required": settings.auth_required,
        "rate_limit_per_minute": settings.rate_limit_per_minute,
        "plan": settings_store.get(db, "plan"),
    }


@router.get("/public-sources", response_model=PublicSourceList)
def public_sources():
    return PublicSourceList(
        items=[SourceOut.model_validate(item) for item in list_public_sources()],
        note="Public stock footage is not a live camera feed; attribution and terms are shown per source.",
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard_summary(db: Session = Depends(get_db)):
    total_videos = db.query(VideoJob).count()
    completed_videos = db.query(VideoJob).filter(VideoJob.status == "completed").count()
    processing_videos = db.query(VideoJob).filter(VideoJob.status.in_(["queued", "processing"])).count()
    latest = db.query(VideoJob).order_by(VideoJob.created_at.desc()).first()
    latest_sample = None
    latest_spaces: list[ParkingSpace] = []
    if latest:
        latest_sample = db.query(DetectionSample).filter(DetectionSample.video_id == latest.id).order_by(DetectionSample.id.desc()).first()
        latest_spaces = db.query(ParkingSpace).filter(ParkingSpace.video_id == latest.id).all()
    occupied = sum(1 for space in latest_spaces if space.state == "occupied")
    free = sum(1 for space in latest_spaces if space.state == "free")
    unknown = len(latest_spaces) - occupied - free
    occupancy = (occupied / len(latest_spaces) * 100) if latest_spaces and occupied + free > 0 else None
    latest_confidence = latest_sample.mean_confidence if latest_sample else (latest.avg_confidence if latest else None)
    peak = db.query(func.max(VideoJob.max_vehicle_count)).filter(VideoJob.status == "completed").scalar()
    return DashboardSummary(
        total_videos=total_videos,
        completed_videos=completed_videos,
        processing_videos=processing_videos,
        latest_video_id=latest.id if latest else None,
        latest_video_name=latest.original_name if latest else None,
        latest_status=latest.status if latest else None,
        vehicles_in_latest_sample=latest_sample.vehicle_count if latest_sample else None,
        peak_vehicles_observed=int(peak) if peak is not None else None,
        configured_spaces=len(latest_spaces),
        occupied_spaces=occupied,
        free_spaces=free,
        unknown_spaces=unknown,
        occupancy_percent=round(occupancy, 1) if occupancy is not None else None,
        latest_confidence=round(latest_confidence, 4) if latest_confidence is not None else None,
        has_data=completed_videos > 0,
    )


@router.get("/videos", response_model=list[VideoJobOut])
def list_videos(db: Session = Depends(get_db)):
    jobs = db.query(VideoJob).order_by(VideoJob.created_at.desc()).limit(100).all()
    return [_video_out(job, db) for job in jobs]


@router.post("/videos/upload", response_model=VideoJobOut, status_code=201, dependencies=[Depends(rate_limit)])
async def upload_video(file: UploadFile = File(...), db: Session = Depends(get_db)):
    billing.check_can_upload(db)
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=415, detail=f"Unsupported file type. Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}")
    file_id = str(uuid.uuid4())
    target = settings.data_path / "uploads" / f"{file_id}{extension}"
    total = 0
    limit = settings.max_upload_mb * 1024 * 1024
    try:
        with target.open("wb") as dest:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > limit:
                    raise HTTPException(status_code=413, detail=f"File exceeds the {settings.max_upload_mb} MB limit")
                dest.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    try:
        job = _make_job(target, file.filename or target.name, db)
    except HTTPException:
        raise
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    activity.record(db, "operator", "video.uploaded", "video", job.id, job.original_name[:120])
    return _video_out(job, db)


@router.post("/public-sources/{source_id}/fetch", response_model=VideoJobOut, status_code=201, dependencies=[Depends(rate_limit)])
async def fetch_public_source(source_id: str, db: Session = Depends(get_db)):
    if not settings_store.get(db, "public_sources_enabled"):
        raise HTTPException(status_code=403, detail="Public-source fetching is disabled by server configuration")
    billing.check_can_upload(db)
    source = PUBLIC_SOURCES.get(source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="Unknown public source")
    target = settings.data_path / "uploads" / f"{uuid.uuid4()}_{source['filename']}"
    byte_limit = settings.max_upload_mb * 1024 * 1024
    downloaded = 0
    try:
        timeout = httpx.Timeout(connect=20, read=120, write=30, pool=20)
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout, headers={"User-Agent": "ParkWiseAI/1.0 (public-footage-fetcher)"}) as client:
            async with client.stream("GET", source["download_url"]) as response:
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").lower()
                content_length = int(response.headers.get("content-length", "0") or 0)
                if content_length and content_length > byte_limit:
                    raise HTTPException(status_code=413, detail=f"Public video exceeds the {settings.max_upload_mb} MB limit")
                if content_type and not ("video" in content_type or "octet-stream" in content_type):
                    raise HTTPException(status_code=415, detail=f"Expected video content, received {content_type}")
                with target.open("wb") as dest:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        downloaded += len(chunk)
                        if downloaded > byte_limit:
                            raise HTTPException(status_code=413, detail=f"Public video exceeds the {settings.max_upload_mb} MB limit")
                        dest.write(chunk)
        if downloaded < 100_000:
            raise ValueError("Downloaded file is unexpectedly small; the public provider may have changed the link.")
        job = _make_job(target, source["filename"], db, source_type="public", source_id=source_id, source_title=source["title"], source_page=source["landing_page"])
        activity.record(db, "operator", "video.imported", "video", job.id, source["title"][:120])
        return _video_out(job, db)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except (httpx.HTTPError, ValueError, OSError) as exc:
        target.unlink(missing_ok=True)
        logger.warning("Could not fetch approved source %s: %s", source_id, exc)
        raise HTTPException(status_code=502, detail=f"Could not fetch public footage: {exc}") from exc
    except Exception as exc:
        target.unlink(missing_ok=True)
        raise HTTPException(status_code=422, detail=f"Could not inspect downloaded footage: {exc}") from exc


@router.get("/videos/{video_id}", response_model=VideoJobOut)
def get_video(video_id: str, db: Session = Depends(get_db)):
    return _video_out(_load_job(video_id, db), db)


@router.delete("/videos/{video_id}", status_code=204, dependencies=[Depends(rate_limit)])
def delete_video(video_id: str, db: Session = Depends(get_db)):
    """Remove a video job, its stored samples and every derived media file on disk."""
    job = _load_job(video_id, db)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait until processing ends before deleting this video")
    deleted_name = job.original_name[:120]
    media_paths = [
        Path(job.file_path),
        Path(job.preview_path) if job.preview_path else None,
        Path(job.processed_video_path) if job.processed_video_path else None,
        # Intermediate OpenCV-written file left behind when H.264 conversion ran.
        settings.data_path / "processed" / f"{video_id}_annotated_opencv.mp4",
        settings.data_path / "processed" / f"{video_id}_annotated_opencv.avi",
    ]
    # OccupancySample has no ORM relationship, so it must be removed before the job row.
    db.query(OccupancySample).filter(OccupancySample.video_id == video_id).delete(synchronize_session=False)
    db.delete(job)  # cascades ParkingSpace and DetectionSample rows
    db.commit()
    activity.record(db, "operator", "video.deleted", "video", video_id, deleted_name)
    for path in media_paths:
        if path is None:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not remove media file for deleted video %s: %s", video_id, path)


@router.post("/videos/{video_id}/process", response_model=VideoJobOut, status_code=202, dependencies=[Depends(rate_limit)])
def process_video(video_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    job = _load_job(video_id, db)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="This video is already queued or processing")
    billing.check_can_process(db)
    # A re-run clears this video's stale measurements so the dashboard cannot double-count them.
    db.query(DetectionSample).filter(DetectionSample.video_id == video_id).delete(synchronize_session=False)
    db.query(OccupancySample).filter(OccupancySample.video_id == video_id).delete(synchronize_session=False)
    for space in db.query(ParkingSpace).filter(ParkingSpace.video_id == video_id).all():
        space.state = "unknown"
        space.confidence = None
        space.last_seen_seconds = None
    job.status = "queued"
    job.progress_percent = 0
    job.current_frame = 0
    job.processed_frames = 0
    job.max_vehicle_count = None
    job.avg_confidence = None
    job.error_message = None
    job.processed_video_path = None
    job.completed_at = None
    db.commit()
    activity.record(db, "operator", "analysis.requested", "video", video_id, job.original_name[:120])
    background_tasks.add_task(process_video_job, video_id)
    return _video_out(job, db)


@router.get("/videos/{video_id}/preview")
def video_preview(video_id: str, db: Session = Depends(get_db)):
    job = _load_job(video_id, db)
    path = Path(job.preview_path) if job.preview_path else None
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Preview image not available")
    return FileResponse(path, media_type="image/jpeg", filename=f"{video_id}-preview.jpg")


@router.get("/videos/{video_id}/original")
def video_original(video_id: str, db: Session = Depends(get_db)):
    job = _load_job(video_id, db)
    path = Path(job.file_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Original video file not available")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(path, media_type=media_type, filename=job.original_name, content_disposition_type="inline")


@router.get("/videos/{video_id}/annotated")
def video_annotated(video_id: str, db: Session = Depends(get_db)):
    job = _load_job(video_id, db)
    if not job.processed_video_path:
        raise HTTPException(status_code=409, detail="Annotated output is not available until analysis completes")
    path = Path(job.processed_video_path)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Annotated output file not found")
    content_type = "video/x-msvideo" if path.suffix.lower() == ".avi" else "video/mp4"
    return FileResponse(path, media_type=content_type, filename=path.name, content_disposition_type="inline")


@router.get("/videos/{video_id}/spaces", response_model=list[SpaceOut])
def list_spaces(video_id: str, db: Session = Depends(get_db)):
    _load_job(video_id, db)
    spaces = db.query(ParkingSpace).filter(ParkingSpace.video_id == video_id).order_by(ParkingSpace.name.asc()).all()
    return [SpaceOut(id=s.id, video_id=s.video_id, name=s.name, polygon=json.loads(s.polygon_json), state=s.state, confidence=s.confidence, last_seen_seconds=s.last_seen_seconds) for s in spaces]


@router.post("/videos/{video_id}/spaces", response_model=SpaceOut, status_code=201, dependencies=[Depends(rate_limit)])
def create_space(video_id: str, payload: SpaceCreate, db: Session = Depends(get_db)):
    job = _load_job(video_id, db)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait until processing ends before changing calibration")
    if db.query(ParkingSpace).filter(ParkingSpace.video_id == video_id, ParkingSpace.name == payload.name).first():
        raise HTTPException(status_code=409, detail="A parking space with this name already exists for the video")
    space = ParkingSpace(id=str(uuid.uuid4()), video_id=video_id, name=payload.name.strip(), polygon_json=json.dumps(payload.polygon), state="unknown")
    db.add(space)
    db.commit()
    db.refresh(space)
    activity.record(db, "operator", "space.created", "space", space.id, f"{space.name} on {job.original_name[:60]}")
    return SpaceOut(id=space.id, video_id=space.video_id, name=space.name, polygon=payload.polygon, state=space.state, confidence=space.confidence, last_seen_seconds=space.last_seen_seconds)


@router.delete("/videos/{video_id}/spaces/{space_id}", status_code=204, dependencies=[Depends(rate_limit)])
def delete_space(video_id: str, space_id: str, db: Session = Depends(get_db)):
    job = _load_job(video_id, db)
    if job.status in {"queued", "processing"}:
        raise HTTPException(status_code=409, detail="Wait until processing ends before changing calibration")
    space = db.query(ParkingSpace).filter(ParkingSpace.id == space_id, ParkingSpace.video_id == video_id).first()
    if not space:
        raise HTTPException(status_code=404, detail="Space not found")
    db.query(OccupancySample).filter(OccupancySample.space_id == space_id).delete(synchronize_session=False)
    db.delete(space)
    db.commit()
    activity.record(db, "operator", "space.deleted", "space", space_id, f"{space.name} on {job.original_name[:60]}")


@router.get("/videos/{video_id}/analytics", response_model=list[DetectionPoint])
def video_analytics(video_id: str, db: Session = Depends(get_db)):
    _load_job(video_id, db)
    samples = db.query(DetectionSample).filter(DetectionSample.video_id == video_id).order_by(DetectionSample.timestamp_seconds.asc()).all()
    return [DetectionPoint(timestamp_seconds=s.timestamp_seconds, frame_number=s.frame_number, vehicle_count=s.vehicle_count, tracked_vehicle_count=s.tracked_vehicle_count, mean_confidence=s.mean_confidence) for s in samples]


@router.get("/videos/{video_id}/occupancy", response_model=OccupancySeries)
def video_occupancy(video_id: str, db: Session = Depends(get_db)):
    """Per-bay occupancy history measured during the last analysis run."""
    _load_job(video_id, db)
    rows = (
        db.query(OccupancySample, ParkingSpace.name)
        .join(ParkingSpace, OccupancySample.space_id == ParkingSpace.id)
        .filter(OccupancySample.video_id == video_id)
        .order_by(OccupancySample.timestamp_seconds.asc(), ParkingSpace.name.asc())
        .all()
    )
    return OccupancySeries(
        items=[
            OccupancyPoint(
                space_id=sample.space_id,
                space_name=name,
                timestamp_seconds=sample.timestamp_seconds,
                state=sample.state,
                confidence=sample.confidence,
            )
            for sample, name in rows
        ]
    )


@router.websocket("/ws/videos/{video_id}")
async def video_job_socket(websocket: WebSocket, video_id: str):
    await websocket.accept()
    try:
        while True:
            db = SessionLocal()
            try:
                job = db.get(VideoJob, video_id)
                if not job:
                    await websocket.send_json({"error": "Video job not found"})
                    await websocket.close(code=1008)
                    return
                await websocket.send_json({
                    "id": job.id,
                    "status": job.status,
                    "progress_percent": job.progress_percent,
                    "current_frame": job.current_frame,
                    "processed_frames": job.processed_frames,
                    "error_message": job.error_message,
                })
                if job.status in {"completed", "failed"}:
                    await websocket.close(code=1000)
                    return
            finally:
                db.close()
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return
