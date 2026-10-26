"""Analytics correctness regressions: occupancy denominator, 0.0 confidence, null-vs-zero."""

import uuid
from datetime import datetime, timezone

from app.models import OccupancySample, ParkingSpace, VideoJob


def _completed_job(db, avg_confidence=None, name="clip.mp4"):
    job = VideoJob(
        id=str(uuid.uuid4()),
        original_name=name,
        file_path=f"/tmp/{uuid.uuid4()}.mp4",
        status="completed",
        duration_seconds=10.0,
        avg_confidence=avg_confidence,
        completed_at=datetime.now(timezone.utc),
    )
    db.add(job)
    db.commit()
    return job


def _space(db, video_id, name="B1"):
    space = ParkingSpace(
        id=str(uuid.uuid4()), video_id=video_id, name=name, polygon_json="[[0,0],[1,0],[1,1]]", state="unknown"
    )
    db.add(space)
    db.commit()
    return space


def _sample(db, video_id, space_id, state):
    db.add(
        OccupancySample(
            video_id=video_id, space_id=space_id, timestamp_seconds=1.0, state=state, confidence=0.5
        )
    )
    db.commit()


class TestOccupancyDenominator:
    def test_unknown_samples_excluded_from_utilisation(self, client, db_session):
        """Utilisation = occupied / (occupied + free); unknown must not dilute it."""
        job = _completed_job(db_session)
        space = _space(db_session, job.id)
        for state in ["occupied", "occupied", "free", "unknown", "unknown", "unknown"]:
            _sample(db_session, job.id, space.id, state)

        payload = client.get("/api/dashboard/analytics").json()
        # 2 occupied / (2 occupied + 1 free) = 66.7%, NOT 2/6 = 33.3%
        assert payload["kpis"]["utilisation_percent"] == 66.7
        reviewed = payload["reviewed_videos"][0]
        assert reviewed["occupied_share_percent"] == 66.7
        assert reviewed["samples"] == 6

    def test_no_observed_states_returns_null(self, client, db_session):
        job = _completed_job(db_session)
        space = _space(db_session, job.id)
        _sample(db_session, job.id, space.id, "unknown")
        _sample(db_session, job.id, space.id, "unknown")

        payload = client.get("/api/dashboard/analytics").json()
        assert payload["kpis"]["utilisation_percent"] is None
        assert payload["reviewed_videos"][0]["occupied_share_percent"] is None


class TestZeroConfidence:
    def test_zero_mean_confidence_is_zero_not_null(self, client, db_session):
        """A measured 0.0 confidence must render as 0.0, never be coerced to None."""
        _completed_job(db_session, avg_confidence=0.0, name="zero-conf.mp4")
        payload = client.get("/api/dashboard/analytics").json()
        assert payload["kpis"]["avg_confidence"] == 0.0
        assert payload["reviewed_videos"][0]["avg_confidence"] == 0.0

    def test_missing_confidence_is_null(self, client, db_session):
        _completed_job(db_session, avg_confidence=None, name="no-conf.mp4")
        payload = client.get("/api/dashboard/analytics").json()
        assert payload["kpis"]["avg_confidence"] is None


class TestEmptyDatabase:
    def test_summary_and_analytics_are_honest_on_empty_db(self, client):
        analytics = client.get("/api/dashboard/analytics").json()
        assert analytics["kpis"]["videos_total"] == 0
        assert analytics["kpis"]["utilisation_percent"] is None
        assert analytics["kpis"]["peak_vehicles"] is None
        assert analytics["charts"]["occupancy_trend"] == []
        summary = client.get("/api/dashboard/summary").json()
        assert summary["has_data"] is False
