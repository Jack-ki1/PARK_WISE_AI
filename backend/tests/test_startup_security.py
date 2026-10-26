"""Startup safety, webhook redirect SSRF guard, and config validation."""

import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app.config import Settings, is_loopback_bind, validate_startup_config
from app.main import _enforce_startup_safety
from app.services import integrations, settings_store


class TestProductionFailClosed:
    def test_production_requires_auth(self):
        settings = Settings(env="production", auth_required=False, allowed_origins="https://app.example.com")
        problems = validate_startup_config(settings)
        assert any("AUTH_REQUIRED" in problem for problem in problems)

    def test_production_rejects_wildcard_cors(self):
        settings = Settings(env="production", auth_required=True, allowed_origins="*")
        problems = validate_startup_config(settings)
        assert any("ORIGINS" in problem for problem in problems)

    def test_production_valid_config_passes(self):
        settings = Settings(
            env="production", auth_required=True, allowed_origins="https://ops.example.com"
        )
        assert validate_startup_config(settings) == []

    def test_development_allows_auth_off(self):
        settings = Settings(env="development", auth_required=False)
        assert validate_startup_config(settings) == []

    def test_enforce_startup_safety_raises_in_production(self, monkeypatch):
        from app.config import settings as env_settings

        monkeypatch.setattr(env_settings, "env", "production", raising=False)
        monkeypatch.setattr(env_settings, "auth_required", False, raising=False)
        with pytest.raises(RuntimeError, match="unsafe configuration"):
            _enforce_startup_safety()

    def test_loopback_detection(self):
        assert is_loopback_bind("127.0.0.1")
        assert is_loopback_bind("localhost")
        assert is_loopback_bind("[::1]")
        assert not is_loopback_bind("0.0.0.0")
        assert not is_loopback_bind("192.168.1.10")


class _RedirectHandler(BaseHTTPRequestHandler):
    """Test server that 302-redirects everything to the metadata endpoint."""

    def do_POST(self):  # noqa: N802
        self.send_response(302)
        self.send_header("Location", "http://169.254.169.254/latest/meta-data/")
        self.end_headers()

    def log_message(self, format, *args):  # silence test output
        pass


class TestWebhookRedirectGuard:
    def test_redirect_is_not_followed(self, db_session, monkeypatch):
        """A webhook that redirects must not be followed (redirect-based SSRF).

        URL validation is bypassed here so the test isolates the redirect guard
        itself; loopback targets are rejected by validate_external_url in real runs.
        """
        monkeypatch.setattr(integrations, "validate_external_url", lambda url, schemes=None, **kw: url)
        server = HTTPServer(("127.0.0.1", 0), _RedirectHandler)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            settings_store.set_many(db_session, {"webhook_url": f"http://127.0.0.1:{port}/hook"})
            result = integrations.dispatch(db_session, "video.completed", {"id": "t"})
            assert result.get("delivered") is not True
            error = str(result.get("error") or "")
            assert "redirect" in error.lower()
        finally:
            server.shutdown()

    def test_unknown_event_rejected(self, db_session):
        result = integrations.dispatch(db_session, "not.an.event", {})
        assert result["delivered"] is False
