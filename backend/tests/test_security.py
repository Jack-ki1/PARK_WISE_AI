"""Security tests: authentication, authorization, SSRF prevention, secret handling.

Auth-mode toggling uses monkeypatch on the live settings object (env vars are
read once at import time, so setenv alone cannot flip auth inside a test).
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings as env_settings
from app.main import app
from app.models import User
from app.security import hash_key, redact_url, validate_external_url


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_user(db_session):
    """Create an admin user for authenticated tests."""
    raw_key = "pk_test_admin_key_12345"
    user = User(
        id="test-admin-001",
        username="testadmin",
        display_name="Test Admin",
        role="admin",
        is_active=True,
        api_key_hash=hash_key(raw_key),
    )
    db_session.add(user)
    db_session.commit()
    return {"user": user, "api_key": raw_key}


@pytest.fixture()
def viewer_user(db_session):
    """Create a viewer user for permission tests."""
    raw_key = "pk_test_viewer_key_67890"
    user = User(
        id="test-viewer-001",
        username="testviewer",
        display_name="Test Viewer",
        role="viewer",
        is_active=True,
        api_key_hash=hash_key(raw_key),
    )
    db_session.add(user)
    db_session.commit()
    return {"user": user, "api_key": raw_key}


@pytest.fixture()
def operator_user(db_session):
    raw_key = "pk_test_operator_key_11111"
    user = User(
        id="test-operator-001",
        username="testoperator",
        display_name="Test Operator",
        role="operator",
        is_active=True,
        api_key_hash=hash_key(raw_key),
    )
    db_session.add(user)
    db_session.commit()
    return {"user": user, "api_key": raw_key}


def _enable_auth(monkeypatch):
    monkeypatch.setattr(env_settings, "auth_required", True, raising=False)


# ============================================================================
# Authentication Tests
# ============================================================================

class TestAuthentication:
    def test_unauthenticated_access_when_auth_disabled(self, client):
        """When auth is disabled, endpoints should be accessible without API key."""
        response = client.get("/api/health")
        assert response.status_code == 200

    def test_unauthenticated_access_blocked_when_auth_enabled(self, client, monkeypatch):
        """When auth is required, unauthenticated requests should be rejected."""
        _enable_auth(monkeypatch)
        response = client.get("/api/users")
        assert response.status_code in [401, 403]

    def test_invalid_api_key_rejected(self, client, monkeypatch):
        """Invalid API keys should be rejected when auth is enabled."""
        _enable_auth(monkeypatch)
        response = client.get("/api/users", headers={"X-API-Key": "invalid_key"})
        assert response.status_code in [401, 403]

    def test_valid_api_key_accepted(self, client, admin_user, monkeypatch):
        """Valid API keys should grant access."""
        _enable_auth(monkeypatch)
        response = client.get(
            "/api/users",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert response.status_code == 200

    def test_auth_required_protects_all_admin_routes(self, client, monkeypatch):
        """With auth on, every admin route rejects anonymous callers."""
        _enable_auth(monkeypatch)
        for method, path in [
            ("GET", "/api/settings"),
            ("GET", "/api/users"),
            ("GET", "/api/billing"),
            ("GET", "/api/system/info"),
        ]:
            response = client.request(method, path)
            assert response.status_code == 401, f"{method} {path}"


# ============================================================================
# Authorization Tests
# ============================================================================

class TestAuthorization:
    def test_viewer_cannot_access_admin_endpoints(self, client, viewer_user):
        """Viewers should not be able to access admin-only endpoints.

        Role checks apply whenever an identity is presented, even with
        PARKWISE_AUTH_REQUIRED=false (identifying yourself must not weaken checks).
        """
        response = client.get(
            "/api/users",
            headers={"X-API-Key": viewer_user["api_key"]}
        )
        assert response.status_code == 403

    def test_viewer_cannot_manage_users_or_settings(self, client, viewer_user):
        headers = {"X-API-Key": viewer_user["api_key"]}
        assert client.put("/api/settings", headers=headers, json={"confidence": 0.4}).status_code == 403
        # NB: body schema validation runs before the handler, so use a valid payload
        # to prove the role gate (not the validator) returns 403.
        assert client.post(
            "/api/users", headers=headers,
            json={"username": "newperson", "display_name": "New", "role": "viewer"},
        ).status_code == 403

    def test_operator_cannot_manage_users(self, client, operator_user):
        """Operators may adjust settings but not user administration."""
        headers = {"X-API-Key": operator_user["api_key"]}
        assert client.get("/api/users", headers=headers).status_code == 403
        assert client.put("/api/settings", headers=headers, json={"confidence": 0.4}).status_code == 200

    def test_admin_can_access_admin_endpoints(self, client, admin_user):
        """Admins should be able to access admin endpoints."""
        response = client.get(
            "/api/users",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert response.status_code == 200

    def test_last_admin_cannot_be_deleted(self, client, admin_user):
        """The last active admin cannot be deleted."""
        response = client.delete(
            f"/api/users/{admin_user['user'].id}",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert response.status_code == 409

    def test_last_admin_cannot_be_demoted_or_disabled(self, client, admin_user):
        headers = {"X-API-Key": admin_user["api_key"]}
        user_id = admin_user["user"].id
        assert client.patch(f"/api/users/{user_id}", headers=headers, json={"role": "viewer"}).status_code == 409
        assert client.patch(f"/api/users/{user_id}", headers=headers, json={"is_active": False}).status_code == 409

    def test_api_key_returned_once_never_echoed(self, client, admin_user, db_session):
        headers = {"X-API-Key": admin_user["api_key"]}
        created = client.post(
            "/api/users", headers=headers,
            json={"username": "temp", "display_name": "Temp", "role": "viewer"},
        )
        assert created.status_code == 201
        raw_key = created.json()["api_key"]
        assert raw_key.startswith("pk_")
        listed = client.get("/api/users", headers=headers).json()
        for item in listed["items"]:
            assert "api_key" not in item
            assert "api_key_hash" not in item
        row = db_session.get(User, "temp") or db_session.query(User).filter_by(username="temp").one()
        assert row.api_key_hash == hash_key(raw_key)
        assert raw_key not in (row.api_key_hash or "")

    def test_user_created_by_admin_records_admin_actor(self, client, admin_user, db_session):
        """Audit actor must be the calling admin, not the newly created user."""
        from app.models import ActivityEvent

        headers = {"X-API-Key": admin_user["api_key"]}
        response = client.post(
            "/api/users", headers=headers,
            json={"username": "created-one", "display_name": "C", "role": "viewer"},
        )
        assert response.status_code == 201
        event = db_session.query(ActivityEvent).filter_by(action="user.created").one()
        assert event.actor == "testadmin"


# ============================================================================
# Secret Handling Tests
# ============================================================================

class TestSecretHandling:
    def test_webhook_secret_not_exposed_in_settings(self, client, admin_user, db_session):
        """Settings endpoint must never return webhook_secret value."""
        from app.services import settings_store
        settings_store.set_many(db_session, {"webhook_secret": "super_secret_value_123"})

        response = client.get(
            "/api/settings",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert response.status_code == 200
        data = response.json()

        assert "webhook_secret" not in data["settings"]
        assert "webhook_secret_configured" in data["settings"]
        assert data["settings"]["webhook_secret_configured"] is True
        assert "super_secret_value_123" not in response.text

    def test_webhook_secret_can_be_rotated(self, client, admin_user):
        """Webhook secret rotation endpoint should work."""
        response = client.post(
            "/api/integrations/webhook/secret",
            headers={"X-API-Key": admin_user["api_key"]},
            json={"action": "set", "secret": "initial_secret"}
        )
        assert response.status_code == 200

        response = client.post(
            "/api/integrations/webhook/secret",
            headers={"X-API-Key": admin_user["api_key"]},
            json={"action": "rotate"}
        )
        assert response.status_code == 200
        data = response.json()

        assert "secret" in data
        assert data["secret"].startswith("ws_") or len(data["secret"]) > 30

        response = client.get(
            "/api/settings",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert "webhook_secret" not in response.json()["settings"]

    def test_direct_webhook_secret_write_blocked(self, client, admin_user):
        """Direct writes to webhook_secret via PUT /api/settings should be blocked."""
        response = client.put(
            "/api/settings",
            headers={"X-API-Key": admin_user["api_key"]},
            json={"webhook_secret": "should_fail"}
        )
        assert response.status_code == 422
        assert "webhook/secret" in response.json()["detail"].lower()

    def test_viewer_cannot_rotate_webhook_secret(self, client, viewer_user):
        response = client.post(
            "/api/integrations/webhook/secret",
            headers={"X-API-Key": viewer_user["api_key"]},
            json={"action": "rotate"},
        )
        assert response.status_code == 403


# ============================================================================
# SSRF Prevention Tests
# ============================================================================

class TestSSRFPrevention:
    def test_metadata_endpoint_blocked(self):
        """Cloud metadata endpoints must be blocked."""
        with pytest.raises(ValueError, match="metadata"):
            validate_external_url("http://169.254.169.254/latest/meta-data/")

    def test_localhost_blocked(self):
        """Loopback addresses must be blocked."""
        with pytest.raises(ValueError, match="not allowed"):
            validate_external_url("rtsp://127.0.0.1:554/stream")

    def test_link_local_blocked(self):
        """Link-local addresses must be blocked."""
        with pytest.raises(ValueError, match="not allowed"):
            validate_external_url("rtsp://169.254.1.1/stream")

    def test_embedded_credentials_blocked(self):
        """URLs with embedded credentials should be rejected."""
        with pytest.raises(ValueError, match="embedded credentials"):
            validate_external_url("rtsp://user:password@camera.local/stream")

    def test_private_camera_allowed_by_default(self):
        """Private network cameras should be allowed by default (CCTV use case)."""
        url = validate_external_url("rtsp://192.168.1.100:554/stream")
        assert url == "rtsp://192.168.1.100:554/stream"

    def test_private_camera_blocked_outside_trusted_cidrs(self):
        """When a trusted-camera allowlist is configured, only those ranges pass."""
        with pytest.raises(ValueError, match="trusted camera"):
            validate_external_url(
                "rtsp://10.9.8.7/stream", trusted_cidrs="192.168.1.0/24"
            )
        # Inside the allowlist is fine.
        assert validate_external_url(
            "rtsp://192.168.1.50/stream", trusted_cidrs="192.168.1.0/24"
        )

    def test_private_blocked_when_disallowed(self):
        """allow_private=False rejects RFC1918 (webhook context)."""
        with pytest.raises(ValueError, match="private address"):
            validate_external_url("https://10.0.0.5/hook", allow_private=False)

    def test_unsupported_scheme_blocked(self):
        """Unsupported URL schemes must be rejected."""
        with pytest.raises(ValueError, match="unsupported scheme"):
            validate_external_url("file:///etc/passwd")

    def test_blocked_hostname(self):
        """Known metadata hostnames must be blocked."""
        with pytest.raises(ValueError, match="not allowed"):
            validate_external_url("http://metadata.google.internal/computeMetadata/v1/")

    def test_percent_encoded_credentials_blocked(self):
        """Percent-encoded userinfo must also be rejected."""
        with pytest.raises(ValueError, match="embedded credentials"):
            validate_external_url("rtsp://user%40corp:pass%40word@192.168.1.5/stream")

    def test_redact_url_strips_userinfo(self):
        assert redact_url("rtsp://admin:secret@192.168.1.5:554/stream") == "rtsp://192.168.1.5:554/stream"
        assert redact_url("rtsp://192.168.1.5/stream") == "rtsp://192.168.1.5/stream"
        assert redact_url(None) is None


# ============================================================================
# WebSocket Ticket Tests
# ============================================================================

class TestWebSocketTickets:
    def test_ticket_creation(self, client, admin_user, db_session):
        """WebSocket tickets can be created for enabled streams."""
        from app.models import Stream

        stream = Stream(
            id="test-stream-001",
            name="Test Camera",
            kind="url",
            url="rtsp://192.168.1.100/stream",
            enabled=True,
        )
        db_session.add(stream)
        db_session.commit()

        response = client.post(
            "/api/streams/test-stream-001/ws-ticket",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert response.status_code == 200
        data = response.json()
        assert "ticket" in data
        assert data["ticket"].startswith("ws_")
        assert "expires_in_seconds" in data

    def test_ticket_not_created_for_disabled_stream(self, client, admin_user, db_session):
        """Tickets cannot be created for disabled streams."""
        from app.models import Stream

        stream = Stream(
            id="test-stream-disabled",
            name="Disabled Camera",
            kind="url",
            url="rtsp://192.168.1.100/stream",
            enabled=False,
        )
        db_session.add(stream)
        db_session.commit()

        response = client.post(
            "/api/streams/test-stream-disabled/ws-ticket",
            headers={"X-API-Key": admin_user["api_key"]}
        )
        assert response.status_code == 403

    def test_ws_rejects_connection_without_ticket_when_auth_enabled(self, client, monkeypatch):
        """With auth on, a WebSocket without ?ticket= is refused (4401)."""
        from starlette.websockets import WebSocketDisconnect

        _enable_auth(monkeypatch)
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect("/api/ws/streams/any"):
                pass
        assert exc_info.value.code == 4401

    def test_ws_rejects_ticket_for_wrong_stream(self, client, admin_user, db_session, monkeypatch):
        """A ticket minted for stream A cannot open stream B."""
        from app.models import Stream
        from starlette.websockets import WebSocketDisconnect

        _enable_auth(monkeypatch)
        db_session.add(Stream(id="stream-a", name="A", kind="url", url="rtsp://192.168.1.1/a", enabled=True))
        db_session.add(Stream(id="stream-b", name="B", kind="url", url="rtsp://192.168.1.1/b", enabled=True))
        db_session.commit()
        ticket = client.post(
            "/api/streams/stream-a/ws-ticket", headers={"X-API-Key": admin_user["api_key"]}
        ).json()["ticket"]
        with pytest.raises(WebSocketDisconnect) as exc_info:
            with client.websocket_connect(f"/api/ws/streams/stream-b?ticket={ticket}"):
                pass
        assert exc_info.value.code == 4401

    def test_ws_ticket_single_use(self, client, admin_user, db_session, monkeypatch):
        """A ticket cannot be replayed for a second connection."""
        import json as jsonlib

        from app.models import Stream
        from starlette.websockets import WebSocketDisconnect

        _enable_auth(monkeypatch)
        # kind=video with a missing job => connection is refused after auth (1011),
        # which still proves ticket validation happened first.
        db_session.add(Stream(id="stream-v", name="V", kind="video", video_id=None, enabled=True))
        db_session.commit()
        ticket = client.post(
            "/api/streams/stream-v/ws-ticket", headers={"X-API-Key": admin_user["api_key"]}
        ).json()["ticket"]
        # First use: passes the ticket gate (accept), then fails on missing source.
        with client.websocket_connect(f"/api/ws/streams/stream-v?ticket={ticket}") as ws:
            error_payload = jsonlib.loads(ws.receive_text())
            assert error_payload["type"] == "error"
            with pytest.raises(WebSocketDisconnect) as first:
                ws.receive_text()
            assert first.value.code == 1011
        # Second use: ticket is consumed => refused at handshake with 4401.
        with pytest.raises(WebSocketDisconnect) as second:
            with client.websocket_connect(f"/api/ws/streams/stream-v?ticket={ticket}"):
                pass
        assert second.value.code == 4401


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
