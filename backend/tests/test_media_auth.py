"""Signed media URLs (C0.1).

`<img>`, `<video>` and browser downloads cannot attach an `X-API-Key` header, so
media endpoints authenticate through short-lived HMAC-signed URLs bound to one
object and one purpose. These tests pin the contract: unsigned => 401 with auth
on, signed => 200, and a signature never works for another object, another
purpose, an expired `exp`, or a non-media endpoint.
"""

import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import settings as env_settings
from app.main import app
from app.models import Stream, User, VideoJob
from app.security import hash_key, sign_media

RAW_KEY = "pk_test_media_key_99999"


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_user(db_session):
    user = User(
        id="media-admin-001",
        username="mediaadmin",
        display_name="Media Admin",
        role="admin",
        is_active=True,
        api_key_hash=hash_key(RAW_KEY),
    )
    db_session.add(user)
    db_session.commit()
    return {"user": user, "api_key": RAW_KEY}


def _enable_auth(monkeypatch) -> None:
    monkeypatch.setattr(env_settings, "auth_required", True, raising=False)


@pytest.fixture()
def video(db_session):
    video_id = str(uuid.uuid4())
    preview = Path(env_settings.data_dir) / "previews" / f"{video_id}.jpg"
    preview.parent.mkdir(parents=True, exist_ok=True)
    preview.write_bytes(b"\xff\xd8\xff\xd9")
    original = Path(env_settings.data_dir) / "uploads" / f"{video_id}.mp4"
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"not-a-real-video")
    job = VideoJob(
        id=video_id,
        original_name="clip.mp4",
        file_path=str(original),
        status="completed",
        preview_path=str(preview),
    )
    db_session.add(job)
    db_session.commit()
    return job


@pytest.fixture()
def stream(db_session):
    stream_id = str(uuid.uuid4())
    snapshot = Path(env_settings.data_dir) / "streams" / f"{stream_id}_calib.jpg"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    snapshot.write_bytes(b"\xff\xd8\xff\xd9")
    row = Stream(id=stream_id, name="Gate camera", kind="url", url="rtsp://example.invalid/live", snapshot_path=str(snapshot))
    db_session.add(row)
    db_session.commit()
    return row


class TestVideoMediaAuth:
    def test_unsigned_preview_rejected_when_auth_enabled(self, client, video, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        assert client.get(f"/api/videos/{video.id}/preview").status_code == 401

    def test_preview_allowed_with_api_key_header(self, client, video, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        response = client.get(f"/api/videos/{video.id}/preview", headers={"X-API-Key": RAW_KEY})
        assert response.status_code == 200

    def test_preview_allowed_with_signed_url(self, client, video, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        url = sign_media(f"/api/videos/{video.id}/preview", "video.preview", video.id)
        assert client.get(url).status_code == 200

    def test_expired_signature_rejected(self, client, video, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        url = sign_media(
            f"/api/videos/{video.id}/preview",
            "video.preview",
            video.id,
            expires_at=int(time.time()) - 10,
        )
        assert client.get(url).status_code == 401

    def test_signature_is_bound_to_object(self, client, video, db_session, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        other_id = str(uuid.uuid4())
        other_preview = Path(env_settings.data_dir) / "previews" / f"{other_id}.jpg"
        other_preview.write_bytes(b"\xff\xd8\xff\xd9")
        other = VideoJob(
            id=other_id,
            original_name="other.mp4",
            file_path=str(other_preview),
            status="completed",
            preview_path=str(other_preview),
        )
        db_session.add(other)
        db_session.commit()
        # Signature minted for `video` must not open `other`'s preview.
        url = sign_media(f"/api/videos/{other_id}/preview", "video.preview", video.id)
        assert client.get(url).status_code == 401
        # ...while the correctly-scoped signature works.
        good = sign_media(f"/api/videos/{other_id}/preview", "video.preview", other_id)
        assert client.get(good).status_code == 200

    def test_signature_is_bound_to_purpose(self, client, video, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        # A preview signature replayed against the original-video endpoint must fail.
        url = sign_media(f"/api/videos/{video.id}/original", "video.preview", video.id)
        assert client.get(url).status_code == 401

    def test_api_returns_signed_media_urls(self, client, video, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        payload = client.get(f"/api/videos/{video.id}", headers={"X-API-Key": RAW_KEY}).json()
        assert payload["preview_url"].startswith(f"/api/videos/{video.id}/preview?")
        assert "sig=" in payload["preview_url"] and "exp=" in payload["preview_url"]

    def test_anonymous_access_when_auth_disabled(self, client, video):
        assert client.get(f"/api/videos/{video.id}/preview").status_code == 200

    def test_json_endpoints_ignore_signatures(self, client, video, admin_user, monkeypatch):
        """A signature only ever authenticates media routes, never the JSON API."""
        _enable_auth(monkeypatch)
        url = sign_media(f"/api/videos/{video.id}", "video.preview", video.id)
        assert client.get(url).status_code == 401


class TestSnapshotMediaAuth:
    def test_unsigned_snapshot_rejected_when_auth_enabled(self, client, stream, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        assert client.get(f"/api/streams/{stream.id}/snapshot").status_code == 401

    def test_signed_snapshot_allowed(self, client, stream, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        url = sign_media(f"/api/streams/{stream.id}/snapshot", "stream.snapshot", stream.id)
        assert client.get(url).status_code == 200

    def test_capture_returns_signed_snapshot_url(self, client, stream, admin_user, monkeypatch):
        _enable_auth(monkeypatch)
        monkeypatch.setattr("app.api.live.snapshot_for", lambda *args, **kwargs: b"\xff\xd8\xff\xd9")
        response = client.post(
            f"/api/streams/{stream.id}/snapshot",
            headers={"X-API-Key": RAW_KEY},
        )
        assert response.status_code == 200
        url = response.json()["snapshot_url"]
        assert "sig=" in url and "exp=" in url
        assert client.get(url).status_code == 200
