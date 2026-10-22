"""Live View streams: SSRF validation, CRUD, calibration, events and guards."""

import uuid

import pytest
from starlette.websockets import WebSocketDisconnect

from app.database import SessionLocal
from app.models import ActivityEvent, Stream, VideoJob


def _seed_video() -> str:
    from app.config import settings

    video_id = str(uuid.uuid4())
    session = SessionLocal()
    session.add(
        VideoJob(
            id=video_id,
            original_name="loop-source.mp4",
            file_path=str(settings.data_path / "uploads" / f"{video_id}.mp4"),
            status="completed",
            duration_seconds=5.0,
        )
    )
    session.commit()
    session.close()
    return video_id


def _cleanup(video_id: str | None = None) -> None:
    session = SessionLocal()
    if video_id:
        job = session.get(VideoJob, video_id)
        if job:
            session.delete(job)
    session.query(Stream).delete()
    session.query(ActivityEvent).filter(ActivityEvent.object_type == "stream").delete()
    session.commit()
    session.close()


def test_stream_rejects_dangerous_sources(client):
    for bad in [
        "file:///etc/passwd",
        "ftp://camera.example/feed",
        "http://169.254.169.254/latest/meta-data/",
        "https://metadata.google.internal/computeMetadata/v1/",
        "rtsp://[::1]/stream",
    ]:
        response = client.post("/api/streams", json={"name": "cam", "kind": "url", "url": bad})
        assert response.status_code == 422, bad
    assert client.get("/api/streams").json()["items"] == []


def test_stream_requires_url_for_kind_url(client):
    response = client.post("/api/streams", json={"name": "cam", "kind": "url"})
    assert response.status_code == 422


def test_stream_requires_existing_video_for_kind_video(client):
    response = client.post(
        "/api/streams", json={"name": "replay", "kind": "video", "video_id": str(uuid.uuid4())}
    )
    assert response.status_code == 422


def test_stream_crud_with_calibration_and_events(client):
    video_id = _seed_video()
    try:
        # 1. create a LAN camera source (private ranges are legitimate CCTV targets)
        created = client.post(
            "/api/streams",
            json={
                "name": "North gate",
                "kind": "url",
                "url": "rtsp://192.168.1.50:554/stream1",
                "target_fps": 4,
                "lat": -25.4,
                "lon": -49.2,
            },
        )
        assert created.status_code == 201, created.text
        stream_id = created.json()["id"]
        assert created.json()["kind"] == "url"
        assert created.json()["status"] == "idle"
        assert created.json()["space_count"] == 0

        # 2. attach calibration (nvdsanalytics-style ROI bays)
        saved = client.put(
            f"/api/streams/{stream_id}/spaces",
            json={
                "spaces": [
                    {"name": "S-01", "polygon": [[0.1, 0.2], [0.4, 0.2], [0.4, 0.6], [0.1, 0.6]]},
                    {"name": "S-02", "polygon": [[0.5, 0.2], [0.8, 0.2], [0.8, 0.6], [0.5, 0.6]]},
                ]
            },
        )
        assert saved.status_code == 200, saved.text
        payload = saved.json()
        assert payload["space_count"] == 2
        assert payload["spaces"][0]["name"] == "S-01"

        # 3. invalid calibration is rejected by the schema
        invalid = client.put(
            f"/api/streams/{stream_id}/spaces",
            json={"spaces": [{"name": "bad", "polygon": [[0.1, 0.1], [0.2, 0.2]]}]},
        )
        assert invalid.status_code == 422

        # 4. events are empty until a session runs
        events = client.get(f"/api/streams/{stream_id}/events")
        assert events.status_code == 200
        assert events.json()["items"] == []

        # 5. disable, then start is refused with 409
        patched = client.patch(f"/api/streams/{stream_id}", json={"enabled": False})
        assert patched.status_code == 200
        assert patched.json()["enabled"] is False
        started = client.post(f"/api/streams/{stream_id}/start")
        assert started.status_code == 409

        # 7. delete removes the record and its activity remains as an audit trail
        assert client.delete(f"/api/streams/{stream_id}").status_code == 204
        assert client.get(f"/api/streams/{stream_id}").status_code == 404

        session = SessionLocal()
        actions = {
            row.action for row in session.query(ActivityEvent).filter(ActivityEvent.object_type == "stream")
        }
        session.close()
        assert {"stream.created", "stream.calibrated", "stream.deleted"} <= actions
    finally:
        _cleanup(video_id)


def test_video_backed_stream_rejects_unknown_video_but_accepts_known(client):
    video_id = _seed_video()
    try:
        created = client.post(
            "/api/streams", json={"name": "replay", "kind": "video", "video_id": video_id}
        )
        assert created.status_code == 201
        assert created.json()["video_id"] == video_id
        stream_id = created.json()["id"]
        # The referenced file does not exist on disk: the capture must fail cleanly (502).
        assert client.post(f"/api/streams/{stream_id}/snapshot").status_code == 502
        assert client.get(f"/api/streams/{stream_id}/snapshot").status_code == 404
        assert client.delete(f"/api/streams/{stream_id}").status_code == 204
    finally:
        _cleanup(video_id)


def test_websocket_unknown_stream_closes_with_policy_violation(client):
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/api/ws/streams/{uuid.uuid4()}"):
            pass
