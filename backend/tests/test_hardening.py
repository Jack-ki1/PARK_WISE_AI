"""Hardening pass tests: quota arithmetic, per-key settings RBAC, job claiming.

These guard the issues recorded in the 2026-10-26 deep review — the billing meter
once reported seconds as minutes, and an operator could lift its own plan through
the generic settings endpoint.
"""

import uuid
from datetime import timedelta

import pytest

from app.config import settings as env_settings
from app.database import SessionLocal
from app.models import User, VideoJob
from app.security import hash_key
from app.services import job_claim, settings_store


def _keyed_user(db_session, *, username: str, role: str) -> dict:
    api_key = f"pk_{username}"
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


def _headers(db_session, *, username: str, role: str) -> dict:
    return {"X-API-Key": _keyed_user(db_session, username=username, role=role)["api_key"]}


def _seed_completed_video(duration_seconds: float) -> str:
    video_id = str(uuid.uuid4())
    session = SessionLocal()
    session.add(
        VideoJob(
            id=video_id,
            original_name="clip.mp4",
            file_path="/tmp/does-not-matter.mp4",
            status="completed",
            width=1920,
            height=1080,
            fps=30.0,
            duration_seconds=duration_seconds,
        )
    )
    session.commit()
    session.close()
    return video_id


class TestBillingArithmetic:
    def test_ten_minute_video_counts_as_ten_minutes_not_six_hundred(self, client, db_session):
        _seed_completed_video(600.0)
        report = client.get("/api/billing").json()
        minutes = report["usage"]["analysis_minutes_this_month"]
        assert minutes == 10.0
        meter = next(m for m in report["meters"] if m["key"] == "analysis_minutes_per_month")
        assert meter["used"] == 10.0
        assert meter["exceeded"] is False

    def test_starter_cap_is_not_tripped_by_a_short_clip(self, client, db_session):
        _seed_completed_video(120.0)
        report = client.get("/api/billing").json()
        assert report["plan"] == "starter"
        assert report["usage"]["analysis_minutes_this_month"] == 2.0


def _seed_job(status: str = "uploaded") -> str:
    video_id = str(uuid.uuid4())
    session = SessionLocal()
    session.add(
        VideoJob(
            id=video_id,
            original_name="clip.mp4",
            file_path="/tmp/does-not-matter.mp4",
            status=status,
            width=1920,
            height=1080,
            fps=30.0,
            duration_seconds=2.0,
        )
    )
    session.commit()
    session.close()
    return video_id


def _row(video_id: str) -> VideoJob:
    session = SessionLocal()
    try:
        job = session.get(VideoJob, video_id)
        session.expunge(job)
        return job
    finally:
        session.close()


class TestJobClaiming:
    def test_only_one_requester_can_queue_a_job(self, db_session):
        video_id = _seed_job("uploaded")
        assert job_claim.enqueue(db_session, video_id) is True
        # A second "Run analysis" click on the same row must lose, not double-queue.
        assert job_claim.enqueue(db_session, video_id) is False
        assert db_session.query(VideoJob).filter(VideoJob.id == video_id).one().status == "queued"

    def test_only_one_worker_can_claim_a_queued_job(self, db_session):
        video_id = _seed_job("queued")
        assert job_claim.claim(db_session, video_id, owner="worker-a") is True
        assert job_claim.claim(db_session, video_id, owner="worker-b") is False
        job = _row(video_id)
        assert job.status == "processing"
        assert job.lease_owner == "worker-a"
        assert job.attempt_count == 1

    def test_heartbeat_is_owner_scoped(self, db_session):
        video_id = _seed_job("queued")
        job_claim.claim(db_session, video_id, owner="worker-a")
        assert job_claim.heartbeat(db_session, video_id, "worker-b") is False
        assert job_claim.heartbeat(db_session, video_id, "worker-a") is True

    def test_expired_lease_becomes_a_visible_failure(self, db_session):
        video_id = _seed_job("queued")
        job_claim.claim(db_session, video_id, owner="worker-a", lease_seconds=-1)
        reaped = job_claim.reap_stale(db_session)
        assert reaped["expired_leases"] == 1
        job = _row(video_id)
        assert job.status == "failed"
        assert "lease expired" in job.error_message

    def test_a_live_lease_is_not_reaped(self, db_session):
        video_id = _seed_job("queued")
        job_claim.claim(db_session, video_id, owner="worker-a")
        assert job_claim.reap_stale(db_session) == {"expired_leases": 0, "abandoned_queue": 0}
        assert _row(video_id).status == "processing"

    def test_a_queued_job_whose_worker_never_started_is_reaped(self, db_session):
        video_id = _seed_job("queued")
        session = SessionLocal()
        job = session.get(VideoJob, video_id)
        job.started_at = job_claim.utcnow() - timedelta(seconds=job_claim.QUEUED_TIMEOUT_SECONDS + 60)
        session.commit()
        session.close()
        assert job_claim.reap_stale(db_session)["abandoned_queue"] == 1
        assert _row(video_id).status == "failed"

    def test_a_freshly_queued_job_is_not_reaped(self, db_session):
        video_id = _seed_job("uploaded")
        job_claim.enqueue(db_session, video_id)
        assert job_claim.reap_stale(db_session) == {"expired_leases": 0, "abandoned_queue": 0}
        assert _row(video_id).status == "queued"

    def test_process_endpoint_rejects_a_second_run(self, client, db_session, monkeypatch):
        # The real pipeline loads OpenCV/Ultralytics; this test is about the queue guard.
        monkeypatch.setattr("app.api.routes.process_video_job", lambda video_id: None)
        # Pro allows two concurrent jobs, so the second request is blocked by the claim
        # race (409) rather than by the Starter quota (402).
        client.put("/api/billing", json={"plan": "pro"})
        video_id = _seed_job("uploaded")
        assert client.post(f"/api/videos/{video_id}/process").status_code == 202
        assert client.post(f"/api/videos/{video_id}/process").status_code == 409

    def test_reaped_job_can_be_requeued(self, client, db_session, monkeypatch):
        monkeypatch.setattr("app.api.routes.process_video_job", lambda video_id: None)
        video_id = _seed_job("queued")
        job_claim.claim(db_session, video_id, owner="dead-worker", lease_seconds=-1)
        job_claim.reap_stale(db_session)
        assert client.post(f"/api/videos/{video_id}/process").status_code == 202


class TestCredentialBruteforceBudget:
    def test_repeated_failed_authentications_get_cut_off(self, client, db_session, monkeypatch):
        from app.security import AUTH_LIMIT_PER_MINUTE, auth_limiter

        auth_limiter._hits.clear()
        monkeypatch.setattr(env_settings, "auth_required", True, raising=False)
        statuses = [client.get("/api/dashboard/summary", headers={"X-API-Key": "pk_wrong"}).status_code
                    for _ in range(AUTH_LIMIT_PER_MINUTE + 5)]
        assert statuses[:AUTH_LIMIT_PER_MINUTE] == [401] * AUTH_LIMIT_PER_MINUTE
        assert 429 in statuses, "an unlimited 401 budget means free DB lookups per guess"

    def test_a_valid_key_is_not_counted_against_the_budget(self, client, db_session, monkeypatch):
        from app.security import AUTH_LIMIT_PER_MINUTE, auth_limiter

        auth_limiter._hits.clear()
        monkeypatch.setattr(env_settings, "auth_required", True, raising=False)
        headers = _headers(db_session, username="ad_auth", role="admin")
        for _ in range(AUTH_LIMIT_PER_MINUTE + 10):
            assert client.get("/api/dashboard/summary", headers=headers).status_code == 200

    def test_proxy_provided_client_address_is_used_when_trusted(self, monkeypatch):
        from types import SimpleNamespace

        from app.security import client_ip

        request = SimpleNamespace(
            headers={"x-forwarded-for": "203.0.113.7, 10.0.0.2"},
            client=SimpleNamespace(host="127.0.0.1"),
        )
        monkeypatch.setattr(env_settings, "trusted_proxy_header", "", raising=False)
        assert client_ip(request) == "127.0.0.1", "the header is forgeable unless the proxy is trusted"
        monkeypatch.setattr(env_settings, "trusted_proxy_header", "x-forwarded-for", raising=False)
        assert client_ip(request) == "203.0.113.7"


class TestWSTicketSingleUse:
    def test_concurrent_redemptions_of_one_ticket_have_exactly_one_winner(self):
        from concurrent.futures import ThreadPoolExecutor

        from app.api import ws_tickets

        ws_tickets.clear()
        ticket = ws_tickets.create_ticket("video", "vid-1")
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: ws_tickets.validate_ticket(ticket, "video", "vid-1"), range(8)))
        assert sum(results) == 1, "a ticket must authenticate exactly one connection"
        ws_tickets.clear()


class TestLiveCoordinateNormalization:
    """The live path compares pixel detections against normalised calibration polygons."""

    BAY = [[0.4, 0.4], [0.6, 0.4], [0.6, 0.6], [0.4, 0.6]]

    def _spaces(self):
        return [{"name": "A-01", "polygon": self.BAY}]

    def test_pixel_center_inside_a_bay_flips_it_occupied(self):
        from app.services.live_stream import BayTracker, normalized_centers

        tracker = BayTracker(self._spaces())
        # A car dead-centre in a 1920x1080 frame: box centre (960, 540) px.
        detections = [(910, 490, 1010, 590, 0.8, 2, 11)]
        centers = normalized_centers(detections, 1920, 1080)
        assert centers[11] == pytest.approx((0.5, 0.5))
        transitions = []
        for _ in range(3):  # the smoothing window needs three agreeing samples
            transitions = tracker.update(list(centers.values())) or transitions
        assert [bay["state"] for bay in tracker.summary()] == ["occupied"]
        # The first decision (unknown -> occupied) is a baseline, not a transition;
        # a later drop is announced.
        assert transitions == []
        for _ in range(6):  # the 5-sample window must clear the occupied votes first
            transitions = tracker.update([]) or transitions
        assert [bay["state"] for bay in tracker.summary()] == ["free"]
        assert transitions and transitions[0]["to"] == "free"

    def test_un_normalised_pixel_centers_never_occupy_a_bay(self):
        from app.services.live_stream import BayTracker

        tracker = BayTracker(self._spaces())
        for _ in range(3):
            tracker.update([(960.0, 540.0)])
        assert [bay["state"] for bay in tracker.summary()] == ["free"], (
            "documents the original bug shape: pixel coordinates miss every 0..1 polygon"
        )

    def test_direction_events_fire_for_normalised_entries(self):
        from app.services.live_stream import DirectionDetector, normalized_centers

        roi = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
        detector = DirectionDetector()
        # A track that starts just off the ROI corner and then moves inside it.
        outside = normalized_centers([(2048, 2048, 2100, 2100, 0.7, 2, 5)], 1920, 1080)
        assert detector.update(outside, roi) == []
        inside = normalized_centers([(910, 490, 1010, 590, 0.7, 2, 5)], 1920, 1080)
        events = detector.update(inside, roi)
        assert events and events[0]["type"] == "line_crossing"
        assert events[0]["direction"] == "in"


class TestWebhookSSRF:
    def test_loopback_webhook_is_blocked(self, db_session):
        from app.services import integrations

        settings_store.set_many(db_session, {"webhook_url": "http://127.0.0.1:9999/hook"}, actor_role="admin")
        result = integrations.dispatch(db_session, "video.completed", {"id": "x"})
        assert result["delivered"] is False
        assert "blocked" in result["error"]

    def test_lan_webhook_is_blocked_even_though_lan_cameras_are_allowed(self, db_session):
        from app.security import validate_external_url
        from app.services import integrations

        # Cameras on a private network are a legitimate source...
        assert validate_external_url("rtsp://192.168.1.50/stream", schemes={"rtsp"})
        # ...but operator-configured egress is not allowed to reach there.
        settings_store.set_many(db_session, {"webhook_url": "http://192.168.1.50/hook"}, actor_role="admin")
        result = integrations.dispatch(db_session, "video.completed", {"id": "x"})
        assert result["delivered"] is False
        assert "private address" in result["error"]

    def test_http_webhook_connects_to_the_validated_address(self, monkeypatch):
        import socket as _socket

        from app.security import pin_validated_url

        real_getaddrinfo = _socket.getaddrinfo

        def fake(host, *args, **kwargs):
            if host == "hooks.example.com":
                return [(2, 1, 6, "", ("93.184.216.34", 0))]
            return real_getaddrinfo(host, *args, **kwargs)

        monkeypatch.setattr(_socket, "getaddrinfo", fake)
        pinned, original = pin_validated_url("http://hooks.example.com:8443/a/b?x=1", schemes={"http"}, allow_private=False)
        assert original == "hooks.example.com"
        assert pinned == "http://93.184.216.34:8443/a/b?x=1"

    def test_https_keeps_the_hostname_for_certificate_validation(self, monkeypatch):
        import socket as _socket

        from app.security import pin_validated_url

        real_getaddrinfo = _socket.getaddrinfo

        def fake(host, *args, **kwargs):
            if host == "hooks.example.com":
                return [(2, 1, 6, "", ("93.184.216.34", 0))]
            return real_getaddrinfo(host, *args, **kwargs)

        monkeypatch.setattr(_socket, "getaddrinfo", fake)
        url, original = pin_validated_url("https://hooks.example.com/a", schemes={"https"}, allow_private=False)
        assert url == "https://hooks.example.com/a"
        assert original is None


class TestPerKeySettingsRBAC:
    def test_operator_cannot_lift_its_own_plan(self, client, db_session):
        headers = _headers(db_session, username="op_rbac", role="operator")
        blocked = client.put("/api/settings", headers=headers, json={"plan": "enterprise"})
        assert blocked.status_code == 403
        assert "plan" in blocked.json()["detail"]
        assert settings_store.get(db_session, "plan") == "starter"

    def test_operator_cannot_redirect_webhooks(self, client, db_session):
        headers = _headers(db_session, username="op_hook", role="operator")
        blocked = client.put(
            "/api/settings",
            headers=headers,
            json={"webhook_url": "https://attacker.example.com/exfil"},
        )
        assert blocked.status_code == 403

    def test_operator_can_still_tune_inference(self, client, db_session):
        headers = _headers(db_session, username="op_tune", role="operator")
        allowed = client.put("/api/settings", headers=headers, json={"confidence": 0.4})
        assert allowed.status_code == 200
        assert allowed.json()["settings"]["confidence"] == 0.4

    def test_admin_can_change_plan_and_billing(self, client, db_session):
        headers = _headers(db_session, username="ad_rbac", role="admin")
        assert client.put("/api/settings", headers=headers, json={"plan": "pro"}).status_code == 200
        assert client.put("/api/billing", headers=headers, json={"plan": "starter"}).status_code == 200

    def test_operator_cannot_change_plan_via_billing_endpoint(self, client, db_session):
        headers = _headers(db_session, username="op_bill", role="operator")
        assert client.put("/api/billing", headers=headers, json={"plan": "enterprise"}).status_code == 403

    def test_schema_advertises_write_roles(self, client):
        schema = client.get("/api/settings").json()["schema"]
        assert schema["plan"]["roles"] == ["admin"]
        assert schema["webhook_url"]["roles"] == ["admin"]
        assert set(schema["confidence"]["roles"]) == {"admin", "operator"}

    def test_mixed_patch_is_rejected_wholly_not_partially(self, client, db_session):
        headers = _headers(db_session, username="op_mix", role="operator")
        rejected = client.put("/api/settings", headers=headers, json={"confidence": 0.5, "plan": "pro"})
        assert rejected.status_code == 403
        assert settings_store.get(db_session, "confidence") != 0.5
