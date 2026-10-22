"""Reports & Settings API: model config, users/roles, billing plans, integrations, system info."""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..database import get_db
from ..models import ActivityEvent, User, VideoJob
from ..schemas import UserCreate, UserPatch, UserOut
from ..security import ROLES, actor_name, current_user, hash_key, rate_limit, require_roles
from ..services import activity, billing, integrations, settings_store

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


def _settings_out(db: Session) -> dict:
    return {
        "settings": settings_store.get_all(db),
        "schema": {
            key: {"type": meta["type"], "choices": meta.get("choices")}
            for key, meta in settings_store.SETTING_SCHEMA.items()
        },
        "plans": settings_store.PLANS,
        "env": {
            "auth_required": env_settings.auth_required,
            "rate_limit_per_minute": env_settings.rate_limit_per_minute,
            "max_upload_mb": env_settings.max_upload_mb,
            "max_video_seconds": env_settings.max_video_seconds,
            "env": env_settings.env,
        },
    }


@router.get("/settings")
def get_settings(db: Session = Depends(get_db)) -> dict:
    return _settings_out(db)


@router.put("/settings", dependencies=[Depends(rate_limit)])
def put_settings(payload: dict, user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin", "operator"])
    if not isinstance(payload, dict) or not payload:
        raise HTTPException(status_code=422, detail="Provide a non-empty object of settings")
    try:
        settings_store.set_many(db, payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None
    activity.record(db, actor_name(user), "settings.updated", "settings", None, ", ".join(payload))
    return _settings_out(db)


@router.get("/users")
def list_users(user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin"])
    rows = db.query(User).order_by(User.created_at.asc()).all()
    items = []
    for row in rows:
        item = UserOut.model_validate(row).model_dump()
        item["has_api_key"] = bool(row.api_key_hash)
        items.append(item)
    return {"items": items}


@router.post("/users", status_code=201, dependencies=[Depends(rate_limit)])
def create_user(payload: UserCreate, user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin"])
    exists = db.query(User).filter(User.username == payload.username).first()
    if exists is not None:
        raise HTTPException(status_code=409, detail="Username already exists")
    raw_key = "pk_" + secrets.token_urlsafe(32)
    user = User(
        id=str(uuid.uuid4()),
        username=payload.username,
        display_name=payload.display_name,
        role=payload.role,
        api_key_hash=hash_key(raw_key),
        created_at=datetime.now(timezone.utc),
    )
    db.add(user)
    db.commit()
    activity.record(db, actor_name(user), "user.created", "user", user.id, f"{user.username} ({user.role})")
    item = UserOut.model_validate(user).model_dump()
    item["has_api_key"] = True
    return {"user": item, "api_key": raw_key, "api_key_note": "Copy it now; it is shown only once."}


@router.patch("/users/{user_id}", dependencies=[Depends(rate_limit)])
def patch_user(user_id: str, payload: UserPatch, user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin"])
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    data = payload.model_dump(exclude_unset=True)
    demoting_admin = user.role == "admin" and ("role" in data and data["role"] != "admin")
    disabling_admin = user.role == "admin" and data.get("is_active") is False
    if (demoting_admin or disabling_admin) and _active_admins(db) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last active admin")
    for key, value in data.items():
        setattr(user, key, value)
    db.commit()
    activity.record(db, actor_name(user), "user.updated", "user", user.id, ", ".join(data))
    item = UserOut.model_validate(user).model_dump()
    item["has_api_key"] = bool(user.api_key_hash)
    return item


@router.post("/users/{user_id}/rotate-key", dependencies=[Depends(rate_limit)])
def rotate_key(user_id: str, user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin"])
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    raw_key = "pk_" + secrets.token_urlsafe(32)
    user.api_key_hash = hash_key(raw_key)
    db.commit()
    activity.record(db, actor_name(user), "user.key_rotated", "user", user.id, user.username)
    return {"user_id": user.id, "api_key": raw_key, "api_key_note": "Copy it now; it is shown only once."}


@router.delete("/users/{user_id}", status_code=204, dependencies=[Depends(rate_limit)])
def delete_user(user_id: str, user=Depends(current_user), db: Session = Depends(get_db)) -> None:
    require_roles(user, ["admin"])
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role == "admin" and user.is_active and _active_admins(db) <= 1:
        raise HTTPException(status_code=409, detail="Cannot remove the last active admin")
    activity.record(db, actor_name(user), "user.deleted", "user", user.id, user.username)
    db.delete(user)
    db.commit()


@router.get("/billing")
def get_billing(db: Session = Depends(get_db)) -> dict:
    report = billing.billing_report(db)
    report["month"] = datetime.now(timezone.utc).strftime("%Y-%m")
    report["videos_total"] = db.query(func.count(VideoJob.id)).scalar() or 0
    return report


@router.put("/billing", dependencies=[Depends(rate_limit)])
def put_billing(payload: dict, user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin", "operator"])
    plan = (payload or {}).get("plan")
    if plan not in settings_store.PLANS:
        raise HTTPException(status_code=422, detail=f"plan must be one of {', '.join(settings_store.PLANS)}")
    settings_store.set_many(db, {"plan": plan})
    activity.record(db, actor_name(user), "billing.plan_changed", "plan", plan, None)
    report = billing.billing_report(db)
    report["month"] = datetime.now(timezone.utc).strftime("%Y-%m")
    return report


@router.post("/integrations/webhook/test", dependencies=[Depends(rate_limit)])
def test_webhook(user=Depends(current_user), db: Session = Depends(get_db)) -> dict:
    require_roles(user, ["admin", "operator"])
    result = integrations.dispatch(
        db,
        "video.completed",
        {"id": "test", "name": "manual test", "status": "completed", "note": "ParkWise webhook test"},
    )
    activity.record(db, actor_name(user), "integrations.webhook_tested", "webhook", None, str(result.get("status") or result.get("error") or "skipped"))
    return result


@router.get("/system/info")
def system_info(db: Session = Depends(get_db)) -> dict:
    """Docs/inventory panel: versions, security posture, model catalog (see docs/SECURITY.md)."""
    return {
        "service": "parkwise-ai-api",
        "env": env_settings.env,
        "python_model_stack": {"default_model": env_settings.model, "ultralytics_license": "AGPL-3.0 / Enterprise (see docs/AI_MODELS.md)"},
        "model_catalog": settings_store.MODEL_CHOICES,
        "security": {
            "auth_required": env_settings.auth_required,
            "rate_limit_per_minute": env_settings.rate_limit_per_minute,
            "roles": list(ROLES),
            "upload_max_mb": env_settings.max_upload_mb,
            "ssrf_schemes_allowed": ["rtsp", "rtsps", "http", "https", "tcp"],
        },
        "docs_url": "/docs",
        "activity_events": db.query(func.count(ActivityEvent.id)).scalar() or 0,
    }


def _active_admins(db: Session) -> int:
    return (
        db.query(func.count(User.id))
        .filter(User.role == "admin", User.is_active.is_(True))
        .scalar()
        or 0
    )
