"""Reports & Settings: model settings, users/roles, billing plans, integrations, rate limits."""

import app.security
from app.database import SessionLocal
from app.models import User


def test_rate_limiter_blocks_bursts_of_mutating_calls(client, monkeypatch):
    # Must run with a clean bucket (this file sorts first): limit to 3 calls/minute.
    monkeypatch.setattr(app.security.env_settings, "rate_limit_per_minute", 3)
    codes = [
        client.post("/api/streams", json={"name": "x", "kind": "url"}).status_code
        for _ in range(4)
    ]
    assert codes[:3] == [422, 422, 422]
    assert codes[3] == 429


def test_settings_expose_schema_plans_and_env(client):
    payload = client.get("/api/settings").json()
    assert "model" in payload["settings"]
    assert payload["schema"]["model"]["choices"]
    assert set(payload["plans"]) == {"starter", "pro", "enterprise"}
    assert payload["env"]["auth_required"] is False
    assert payload["env"]["rate_limit_per_minute"] > 0


def test_settings_patch_validates_and_persists(client):
    before = client.get("/api/config/public").json()["confidence"]
    try:
        response = client.put("/api/settings", json={"confidence": 0.42, "multiscale": False})
        assert response.status_code == 200
        assert response.json()["settings"]["confidence"] == 0.42
        assert client.get("/api/config/public").json()["confidence"] == 0.42

        assert client.put("/api/settings", json={"confidence": 4.2}).status_code == 422
        assert client.put("/api/settings", json={"model": "yolo99.tiny"}).status_code == 422
        assert client.put("/api/settings", json={"not_a_setting": 1}).status_code == 422
        assert client.put("/api/settings", json={}).status_code == 422
    finally:
        client.put("/api/settings", json={"confidence": before, "multiscale": True})
    assert client.get("/api/config/public").json()["confidence"] == before


def test_users_lifecycle_and_last_admin_guard(client):
    created = client.post(
        "/api/users",
        json={"username": "dana", "display_name": "Dana Operator", "role": "admin"},
    )
    assert created.status_code == 201, created.text
    body = created.json()
    user_id = body["user"]["id"]
    raw_key = body["api_key"]
    assert raw_key.startswith("pk_")
    assert body["user"]["has_api_key"] is True

    assert (
        client.post(
            "/api/users", json={"username": "dana", "display_name": "Dup", "role": "viewer"}
        ).status_code
        == 409
    )

    listed = client.get("/api/users").json()["items"]
    assert [row["username"] for row in listed] == ["dana"]

    # Guard: the only active admin cannot be demoted or removed.
    assert (
        client.patch(f"/api/users/{user_id}", json={"role": "viewer"}).status_code == 409
    )
    assert client.delete(f"/api/users/{user_id}").status_code == 409

    second = client.post(
        "/api/users", json={"username": "sam", "display_name": "Sam Admin", "role": "admin"}
    ).json()
    second_id = second["user"]["id"]
    demoted = client.patch(f"/api/users/{user_id}", json={"role": "viewer"})
    assert demoted.status_code == 200
    assert demoted.json()["role"] == "viewer"
    # Guard: the single remaining active admin cannot be deactivated.
    assert client.patch(f"/api/users/{second_id}", json={"is_active": False}).status_code == 409

    rotated = client.post(f"/api/users/{user_id}/rotate-key").json()
    assert rotated["api_key"].startswith("pk_")
    assert rotated["api_key"] != raw_key

    # Restore two admins, remove one, then prove the last active admin is protected.
    assert client.patch(f"/api/users/{user_id}", json={"role": "admin"}).status_code == 200
    assert client.delete(f"/api/users/{second_id}").status_code == 204
    assert client.delete(f"/api/users/{user_id}").status_code == 409
    assert [row["username"] for row in client.get("/api/users").json()["items"]] == ["dana"]

    session = SessionLocal()
    session.query(User).delete()
    session.commit()
    session.close()


def test_api_key_authentication_is_enforced_when_required(client, monkeypatch):
    created = client.post(
        "/api/users", json={"username": "ivy", "display_name": "Ivy", "role": "admin"}
    ).json()
    api_key = created["api_key"]
    user_id = created["user"]["id"]
    try:
        monkeypatch.setattr(app.security.env_settings, "auth_required", True)
        assert client.get("/api/settings").status_code == 401
        assert client.get("/api/settings", headers={"X-API-Key": "pk_wrong"}).status_code == 401
        ok = client.get("/api/settings", headers={"X-API-Key": api_key})
        assert ok.status_code == 200
        bearer = client.get("/api/settings", headers={"Authorization": f"Bearer {api_key}"})
        assert bearer.status_code == 200
    finally:
        monkeypatch.setattr(app.security.env_settings, "auth_required", False)
        session = SessionLocal()
        user = session.get(User, user_id)
        if user:
            session.delete(user)
        session.commit()
        session.close()


def test_billing_reports_plan_usage_and_accepts_upgrades(client):
    report = client.get("/api/billing").json()
    assert report["plan"] == "starter"
    assert len(report["meters"]) == 5
    assert report["plan_info"]["limits"]["videos_per_month"] == 10

    upgraded = client.put("/api/billing", json={"plan": "pro"})
    assert upgraded.status_code == 200
    assert upgraded.json()["plan"] == "pro"
    assert upgraded.json()["plan_info"]["price_month_usd"] == 149

    assert client.put("/api/billing", json={"plan": "enterprise-plus"}).status_code == 422
    assert client.put("/api/settings", json={"plan": "pro"}).status_code == 200
    assert client.put("/api/settings", json={"plan": "nope"}).status_code == 422

    client.put("/api/billing", json={"plan": "starter"})
    assert client.get("/api/billing").json()["plan"] == "starter"


def test_webhook_test_reports_skipped_without_configuration(client):
    response = client.post("/api/integrations/webhook/test")
    assert response.status_code == 200
    body = response.json()
    assert body.get("skipped") is True


def test_webhook_url_must_be_http(client):
    assert (
        client.put("/api/settings", json={"webhook_url": "file:///tmp/hook"}).status_code == 422
    )
    assert client.put("/api/settings", json={"webhook_url": None}).status_code == 200


def test_system_info_lists_models_and_security_posture(client):
    payload = client.get("/api/system/info").json()
    assert "yolo26s.pt" in payload["model_catalog"]
    assert "rtdetr-l.pt" in payload["model_catalog"]
    assert payload["security"]["roles"] == ["admin", "operator", "viewer"]
    assert payload["security"]["auth_required"] is False
