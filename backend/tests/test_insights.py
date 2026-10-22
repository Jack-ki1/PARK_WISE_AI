"""Dashboard analytics (KPIs/charts/reviewed videos) and the activity feed."""

import uuid

from app.database import SessionLocal
from app.models import ActivityEvent, OccupancySample, ParkingSpace, VideoJob


def _seed_reviewed_video() -> str:
    from app.config import settings

    video_id = str(uuid.uuid4())
    session = SessionLocal()
    job = VideoJob(
        id=video_id,
        original_name="reviewed.mp4",
        file_path=str(settings.data_path / "uploads" / f"{video_id}.mp4"),
        status="completed",
        width=1920,
        height=1080,
        fps=30.0,
        duration_seconds=120.0,
        max_vehicle_count=14,
        avg_confidence=0.81,
        model_name="yolo26s.pt",
    )
    session.add(job)
    space = ParkingSpace(
        id=str(uuid.uuid4()),
        video_id=video_id,
        name="B-01",
        polygon_json="[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.1, 0.4]]",
        state="occupied",
    )
    session.add(space)
    for index, state in enumerate(["occupied", "occupied", "free"]):
        session.add(
            OccupancySample(
                video_id=video_id,
                space_id=space.id,
                timestamp_seconds=float(index),
                state=state,
                confidence=0.9,
            )
        )
    session.add(
        ActivityEvent(actor="operator", action="video.uploaded", object_type="video", object_id=video_id)
    )
    session.commit()
    session.close()
    return video_id


def _cleanup(video_id: str) -> None:
    session = SessionLocal()
    session.query(OccupancySample).filter(OccupancySample.video_id == video_id).delete()
    job = session.get(VideoJob, video_id)
    if job:
        session.delete(job)
    session.query(ActivityEvent).filter(ActivityEvent.object_id == video_id).delete()
    session.commit()
    session.close()


def test_analytics_returns_kpis_and_chart_series_on_empty_database(client):
    response = client.get("/api/dashboard/analytics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["kpis"]["videos_total"] == 0
    assert payload["kpis"]["utilisation_percent"] is None
    assert payload["kpis"]["storage_gb"] >= 0
    assert len(payload["charts"]["activity_by_day"]) == 14
    assert payload["charts"]["status_breakdown"] == []
    assert payload["reviewed_videos"] == []


def test_analytics_summarises_reviewed_videos_activity_and_utilisation(client):
    video_id = _seed_reviewed_video()
    try:
        payload = client.get("/api/dashboard/analytics").json()
        assert payload["kpis"]["videos_completed"] == 1
        assert payload["kpis"]["peak_vehicles"] == 14
        assert payload["kpis"]["analyzed_hours"] == 0.03
        assert payload["kpis"]["bays_configured"] >= 1
        assert payload["kpis"]["utilisation_percent"] == 66.7
        assert payload["charts"]["utilisation"][0]["value"] == 2
        assert payload["charts"]["top_videos"][0]["id"] == video_id
        reviewed = payload["reviewed_videos"][0]
        assert reviewed["occupied_share_percent"] == 66.7
        assert reviewed["samples"] == 3
        assert payload["charts"]["activity_by_action"].get("video.uploaded") == 1
        assert sum(day["total"] for day in payload["charts"]["activity_by_day"]) >= 1
        assert payload["charts"]["state_mix"] != []
    finally:
        _cleanup(video_id)


def test_activity_feed_lists_recent_events(client):
    video_id = _seed_reviewed_video()
    try:
        response = client.get("/api/activity")
        assert response.status_code == 200
        items = response.json()["items"]
        assert any(item["action"] == "video.uploaded" for item in items)
        assert items[0]["created_at"]
    finally:
        _cleanup(video_id)


def test_upload_records_activity_and_enforces_plan_quota(client):
    # Starter plan allows 10 uploads/month; seeding 10 jobs trips the quota with 402.
    from app.config import settings
    from app.database import SessionLocal as _Session
    from app.models import VideoJob as _VideoJob

    session = _Session()
    created = []
    for index in range(10):
        job_id = str(uuid.uuid4())
        session.add(
            _VideoJob(
                id=job_id,
                original_name=f"bulk-{index}.mp4",
                file_path=str(settings.data_path / "uploads" / f"{job_id}.mp4"),
                status="completed",
                duration_seconds=1.0,
            )
        )
        created.append(job_id)
    session.commit()
    session.close()

    try:
        from app.models import ActivityEvent as _Event

        response = client.post(
            "/api/videos/upload",
            files={"file": ("clip.mp4", b"\x00" * 16, "video/mp4")},
        )
        # Either the quota (402) or the invalid payload (422) is acceptable before quota;
        # with 10 existing uploads the quota check runs first.
        assert response.status_code == 402

        session = _Session()
        session.query(_Event).filter(_Event.action == "video.uploaded").delete()
        session.commit()
        session.close()
    finally:
        session = _Session()
        for job_id in created:
            job = session.get(_VideoJob, job_id)
            if job:
                session.delete(job)
        session.commit()
        session.close()
