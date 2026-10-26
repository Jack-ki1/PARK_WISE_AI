"""Regression tests for the session-5 hardening pass.

Covers: role gates on the video/stream writers, cleanup on delete (detached
replay streams, orphaned derived media, calibration snapshots), the job-progress
WebSocket ticket flow, dashboard utilisation maths, the billing PUT payload and
viewer-independent stream lifecycle semantics.
"""

import io
import json
import time
import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from app.config import settings as env_settings
from app.database import SessionLocal
from app.models import ParkingSpace, Stream, User, VideoJob
from app.security import hash_key
from app.services.live_stream import StreamSession, manager


def _keyed_user(db_session, *, username: str, role: str, api_key: str) -> dict:
    user = User(
        id=str(uuid.uuid4()),
        username=username,
        display_name=username.title(),
        role=role,
        is_active=True,
        api_key_hash=hash_key(api_key),
    )
    db_session.add(user)
    db_session.commit()
    return {"user": user, "api_key": api_key}


def _seed_video(status: str = "uploaded", with_media: bool = False) -> str:
    video_id = str(uuid.uuid4())
    upload = env_settings.data_path / "uploads" / f"{video_id}.mp4"
    preview = env_settings.data_path / "previews" / f"{video_id}.jpg"
    annotated = env_settings.data_path / "processed" / f"{video_id}_annotated.mp4"
    upload.parent.mkdir(parents=True, exist_ok=True)
    upload.write_bytes(b"source")
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"preview")
    if with_media:
        annotated.parent.mkdir(parents=True, exist_ok=True)
        annotated.write_bytes(b"annotated")
    session = SessionLocal()
    session.add(
        VideoJob(
            id=video_id,
            original_name="clip.mp4",
            file_path=str(upload),
            preview_path=str(preview),
            status=status,
            width=1920,
            height=1080,
            fps=30.0,
            duration_seconds=2.0,
            processed_video_path=str(annotated) if with_media else None,
        )
    )
    session.commit()
    session.close()
    return video_id


class TestRoleGatesOnVideoAndStreamWriters:
    def test_viewer_cannot_mutate_video_jobs(self, client, db_session):
        headers = {"X-API-Key": _keyed_user(db_session, username="viewer1", role="viewer", api_key="pk_v1")["api_key"]}
        video_id = _seed_video()

        upload = client.post(
            "/api/videos/upload",
            headers=headers,
            files={"file": ("clip.mp4", io.BytesIO(b"x"), "video/mp4")},
        )
        assert upload.status_code == 403

        assert client.post(f"/api/videos/{video_id}/process", headers=headers).status_code == 403
        assert client.post(
            f"/api/videos/{video_id}/spaces",
            headers=headers,
            json={"name": "B1", "polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]},
        ).status_code == 403
        assert client.delete(f"/api/videos/{video_id}", headers=headers).status_code == 403
        # Reading stays open to every role.
        assert client.get(f"/api/videos/{video_id}", headers=headers).status_code == 200

    def test_viewer_cannot_manage_streams(self, client, db_session):
        headers = {"X-API-Key": _keyed_user(db_session, username="viewer2", role="viewer", api_key="pk_v2")["api_key"]}
        created = client.post(
            "/api/streams",
            headers=headers,
            json={"name": "Nope", "kind": "url", "url": "rtsp://192.168.1.50/stream"},
        )
        assert created.status_code == 403

        stream_id = str(uuid.uuid4())
        session = SessionLocal()
        session.add(Stream(id=stream_id, name="Cam", kind="url", url="rtsp://192.168.1.50/s", enabled=True))
        session.commit()
        session.close()

        assert client.post(f"/api/streams/{stream_id}/start", headers=headers).status_code == 403
        assert client.post(f"/api/streams/{stream_id}/stop", headers=headers).status_code == 403
        assert client.delete(f"/api/streams/{stream_id}", headers=headers).status_code == 403
        assert client.get(f"/api/streams/{stream_id}", headers=headers).status_code == 200

    def test_operator_is_allowed(self, client, db_session):
        headers = {"X-API-Key": _keyed_user(db_session, username="op1", role="operator", api_key="pk_o1")["api_key"]}
        video_id = _seed_video()
        assert client.post(
            f"/api/videos/{video_id}/spaces",
            headers=headers,
            json={"name": "B1", "polygon": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]},
        ).status_code == 201


class TestDeleteCleanup:
    def test_delete_video_detaches_stream_and_removes_derived_media(self, client, db_session):
        video_id = _seed_video(with_media=True)
        stream_id = str(uuid.uuid4())
        annotated = env_settings.data_path / "processed" / f"{video_id}_annotated.mp4"
        upload = env_settings.data_path / "uploads" / f"{video_id}.mp4"
        preview = env_settings.data_path / "previews" / f"{video_id}.jpg"
        assert annotated.exists()
        session = SessionLocal()
        session.add(Stream(id=stream_id, name="Replay", kind="video", video_id=video_id, enabled=True))
        session.commit()
        session.close()

        assert client.delete(f"/api/videos/{video_id}").status_code == 204

        assert not annotated.exists() and not upload.exists() and not preview.exists()
        session = SessionLocal()
        row = session.get(Stream, stream_id)
        session.close()
        assert row is not None, "stream itself must survive"
        assert row.video_id is None, "dangling video_id would break the next start"

    def test_delete_stream_removes_calibration_snapshot(self, client, db_session):
        stream_id = str(uuid.uuid4())
        snapshot = env_settings.data_path / "streams" / f"{stream_id}_calib.jpg"
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_bytes(b"jpeg")
        session = SessionLocal()
        session.add(
            Stream(id=stream_id, name="Cam", kind="url", url="rtsp://192.168.1.50/s", enabled=True, snapshot_path=str(snapshot))
        )
        session.commit()
        session.close()

        assert client.delete(f"/api/streams/{stream_id}").status_code == 204
        assert not snapshot.exists()
        session = SessionLocal()
        assert session.get(Stream, stream_id) is None
        session.close()


class TestVideoProgressTicket:
    def test_ticket_is_single_use_and_scoped(self, client, db_session, monkeypatch):
        video_id = _seed_video()
        monkeypatch.setattr(env_settings, "auth_required", True, raising=False)
        headers = {"X-API-Key": _keyed_user(db_session, username="ticketop", role="operator", api_key="pk_tk1")["api_key"]}

        with pytest.raises(WebSocketDisconnect) as rejected:
            with client.websocket_connect(f"/api/ws/videos/{video_id}"):
                pass
        assert rejected.value.code == 4401

        ticket = client.post(f"/api/videos/{video_id}/ws-ticket", headers=headers).json()["ticket"]
        assert ticket.startswith("ws_")
        # Wrong video id: ticket is refused but remains usable for its own video.
        other = _seed_video()
        with pytest.raises(WebSocketDisconnect) as wrong:
            with client.websocket_connect(f"/api/ws/videos/{other}?ticket={ticket}"):
                pass
        assert wrong.value.code == 4401

        with client.websocket_connect(f"/api/ws/videos/{video_id}?ticket={ticket}") as ws:
            payload = json.loads(ws.receive_text())
            assert payload["id"] == video_id
        with pytest.raises(WebSocketDisconnect) as replay:
            with client.websocket_connect(f"/api/ws/videos/{video_id}?ticket={ticket}"):
                pass
        assert replay.value.code == 4401

    def test_expired_ticket_rejected(self, client, db_session, monkeypatch):
        from app.api import ws_tickets

        video_id = _seed_video()
        monkeypatch.setattr(env_settings, "auth_required", True, raising=False)
        headers = {"X-API-Key": _keyed_user(db_session, username="ticketop2", role="operator", api_key="pk_tk2")["api_key"]}
        ticket = client.post(f"/api/videos/{video_id}/ws-ticket", headers=headers).json()["ticket"]
        ws_tickets._tickets[ticket]["expires_at"] = time.time() - 1

        with pytest.raises(WebSocketDisconnect) as expired:
            with client.websocket_connect(f"/api/ws/videos/{video_id}?ticket={ticket}"):
                pass
        assert expired.value.code == 4401
        assert ticket not in ws_tickets._tickets

    def test_ticket_endpoint_requires_existing_video(self, client):
        assert client.post(f"/api/videos/{uuid.uuid4()}/ws-ticket").status_code == 404


class TestDashboardMaths:
    def test_unknown_bays_do_not_dilute_utilisation(self, client, db_session):
        video_id = _seed_video(status="completed")
        session = SessionLocal()
        session.query(VideoJob).filter(VideoJob.id == video_id).update({"max_vehicle_count": 4})
        for index, state in enumerate(["occupied", "occupied", "occupied", "unknown"]):
            session.add(
                ParkingSpace(
                    id=str(uuid.uuid4()),
                    video_id=video_id,
                    name=f"B{index}",
                    polygon_json="[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]",
                    state=state,
                )
            )
        session.commit()
        session.close()

        summary = client.get("/api/dashboard/summary").json()
        assert summary["configured_spaces"] == 4
        assert summary["unknown_spaces"] == 1
        # 3 occupied out of 3 *observed* bays: the unknown bay is not counted as free.
        assert summary["occupancy_percent"] == 100.0


class TestBillingShape:
    def test_put_billing_returns_videos_total(self, client, db_session):
        _seed_video(status="completed")
        put = client.put("/api/billing", json={"plan": "pro"})
        assert put.status_code == 200
        assert put.json()["videos_total"] == 1
        assert put.json()["plan"] == "pro"
        assert client.get("/api/billing").json()["videos_total"] == 1


class TestStreamLifecycle:
    def test_explicit_start_is_not_stopped_when_viewers_leave(self, db_session):
        stream_id = str(uuid.uuid4())
        session = SessionLocal()
        stream = Stream(id=stream_id, name="Cam", kind="url", url="rtsp://192.168.1.50/s", enabled=True)
        session.add(stream)
        session.commit()
        try:
            # Session created the way POST /start creates it (explicit=True).
            started = StreamSession(stream, "rtsp://192.168.1.50/s", [], {})
            started.explicitly_started = True
            manager._sessions[stream_id] = started
            manager.stop_if_idle(stream_id)
            assert manager.get(stream_id) is started, "operator-started session must survive viewer disconnect"

            # A viewer-started session (explicit=False) is released instead.
            watched = StreamSession(stream, "rtsp://192.168.1.50/s", [], {})
            manager._sessions[stream_id] = watched
            manager.stop_if_idle(stream_id)
            assert manager.get(stream_id) is None
        finally:
            manager.stop(stream_id, timeout=1.0)

    def test_start_endpoint_marks_session_explicit(self, client, db_session):
        video_id = _seed_video(status="completed")
        stream_id = str(uuid.uuid4())
        session = SessionLocal()
        session.add(Stream(id=stream_id, name="Replay", kind="video", video_id=video_id, enabled=True, target_fps=2))
        session.commit()
        session.close()
        try:
            response = client.post(f"/api/streams/{stream_id}/start")
            assert response.status_code == 200
            active = manager.get(stream_id)
            assert active is not None and active.explicitly_started is True
            manager.stop_if_idle(stream_id)
            assert manager.get(stream_id) is active
        finally:
            manager.stop(stream_id, timeout=2.0)
