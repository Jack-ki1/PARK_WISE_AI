"""Video deletion and per-bay occupancy history endpoints."""

import uuid

from app.database import SessionLocal
from app.models import OccupancySample, ParkingSpace, VideoJob


def _seed_video(status: str = "completed", files: bool = False) -> tuple[str, list]:
    from app.config import settings

    video_id = str(uuid.uuid4())
    paths = []
    if files:
        upload = settings.data_path / "uploads" / f"{video_id}.mp4"
        preview = settings.data_path / "previews" / f"{video_id}.jpg"
        for path in (upload, preview):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"test-media")
            paths.append(path)
    else:
        upload = settings.data_path / "uploads" / f"{video_id}.mp4"
        preview = settings.data_path / "previews" / f"{video_id}.jpg"
    job = VideoJob(
        id=video_id,
        original_name="fixture.mp4",
        file_path=str(upload),
        preview_path=str(preview),
        status=status,
        width=1920,
        height=1080,
        fps=30.0,
        duration_seconds=2.0,
    )
    session = SessionLocal()
    session.add(job)
    session.commit()
    session.close()
    return video_id, paths


def _seed_space_and_occupancy(video_id: str) -> str:
    session = SessionLocal()
    space = ParkingSpace(
        id=str(uuid.uuid4()),
        video_id=video_id,
        name="A-01",
        polygon_json='[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2], [0.1, 0.2]]',
        state="occupied",
    )
    session.add(space)
    session.add(OccupancySample(video_id=video_id, space_id=space.id, timestamp_seconds=0.5, state="occupied", confidence=0.9))
    session.add(OccupancySample(video_id=video_id, space_id=space.id, timestamp_seconds=1.0, state="free", confidence=None))
    session.commit()
    session.close()
    return space.id


def test_delete_video_removes_record_and_media(client):
    video_id, paths = _seed_video(files=True)
    response = client.delete(f"/api/videos/{video_id}")
    assert response.status_code == 204
    assert client.get(f"/api/videos/{video_id}").status_code == 404
    assert all(not path.exists() for path in paths)


def test_delete_video_cascades_spaces_and_samples(client):
    video_id, _ = _seed_video()
    _seed_space_and_occupancy(video_id)
    assert client.delete(f"/api/videos/{video_id}").status_code == 204

    session = SessionLocal()
    assert session.query(ParkingSpace).filter(ParkingSpace.video_id == video_id).count() == 0
    assert session.query(OccupancySample).filter(OccupancySample.video_id == video_id).count() == 0
    session.close()


def test_delete_video_unknown_id_returns_404(client):
    assert client.delete(f"/api/videos/{uuid.uuid4()}").status_code == 404


def test_delete_video_rejects_jobs_that_are_still_processing(client):
    video_id, _ = _seed_video(status="processing")
    assert client.delete(f"/api/videos/{video_id}").status_code == 409

    session = SessionLocal()
    assert session.get(VideoJob, video_id) is not None
    session.delete(session.get(VideoJob, video_id))
    session.commit()
    session.close()


def test_occupancy_series_is_empty_without_measured_bays(client):
    video_id, _ = _seed_video()
    response = client.get(f"/api/videos/{video_id}/occupancy")
    assert response.status_code == 200
    assert response.json() == {"items": []}

    session = SessionLocal()
    session.delete(session.get(VideoJob, video_id))
    session.commit()
    session.close()


def test_occupancy_series_returns_measured_points_with_bay_names(client):
    video_id, _ = _seed_video()
    _seed_space_and_occupancy(video_id)
    response = client.get(f"/api/videos/{video_id}/occupancy")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["space_name"] for item in items] == ["A-01", "A-01"]
    assert [item["state"] for item in items] == ["occupied", "free"]
    assert items[0]["confidence"] == 0.9
    assert items[1]["confidence"] is None

    session = SessionLocal()
    session.delete(session.get(VideoJob, video_id))
    session.commit()
    session.close()


def test_occupancy_series_unknown_video_returns_404(client):
    assert client.get(f"/api/videos/{uuid.uuid4()}/occupancy").status_code == 404
