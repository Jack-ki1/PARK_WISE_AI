"""Persistent settings that override env defaults, plus plan/billing definitions.

Settings live in the `app_settings` table as JSON values so the dashboard can change
inference, integration and billing keys without a redeploy. Environment variables
(`PARKWISE_*`) remain the baseline; DB values win.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..models import AppSetting

MODEL_CHOICES = [
    "yolo26n.pt",
    "yolo26s.pt",
    "yolo26m.pt",
    "yolo26l.pt",
    "yolo26x.pt",
    "yolo11n.pt",
    "yolo11s.pt",
    "yolo11m.pt",
    "yolo11l.pt",
    "yolo11x.pt",
    "rtdetr-l.pt",
    "rtdetr-x.pt",
]

DEVICE_CHOICES = ["auto", "cpu", "cuda", "mps"]

# Writable keys -> (type, validator). Anything else is rejected (mass-assignment guard).
def _choice(options: list[str]):
    def check(value: Any) -> str:
        value = str(value)
        if value not in options:
            raise ValueError(f"must be one of: {', '.join(options)}")
        return value

    return check


def _number(minimum: float, maximum: float, cast: type = float):
    def check(value: Any) -> Any:
        try:
            number = cast(value)
        except (TypeError, ValueError):
            raise ValueError(f"must be a number between {minimum} and {maximum}") from None
        if not minimum <= number <= maximum:
            raise ValueError(f"must be between {minimum} and {maximum}")
        return number

    return check


def _flag(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if str(value).lower() in {"1", "true", "yes", "on"}:
        return True
    if str(value).lower() in {"0", "false", "no", "off"}:
        return False
    raise ValueError("must be a boolean")


def _url(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value).strip()
    if not text.lower().startswith(("http://", "https://")):
        raise ValueError("must be an http(s) URL")
    if len(text) > 500:
        raise ValueError("must be 500 characters or fewer")
    return text


def _secret(value: Any) -> str | None:
    if value in (None, ""):
        return None
    text = str(value)
    if len(text) > 200:
        raise ValueError("must be 200 characters or fewer")
    return text


def _map_center(value: Any) -> list[float] | None:
    if value in (None, "", []):
        return None
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        raise ValueError("must be [latitude, longitude]")
    try:
        lat, lon = float(value[0]), float(value[1])
    except (TypeError, ValueError):
        raise ValueError("must be [latitude, longitude]") from None
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("latitude/longitude out of range")
    return [lat, lon]


PLANS: dict[str, dict[str, Any]] = {
    "starter": {
        "name": "Starter",
        "price_month_usd": 0,
        "blurb": "Single lot, occasional reviews.",
        "limits": {
            "videos_per_month": 10,
            "analysis_minutes_per_month": 60,
            "streams": 1,
            "storage_gb": 5,
            "concurrent_jobs": 1,
        },
    },
    "pro": {
        "name": "Pro",
        "price_month_usd": 149,
        "blurb": "Live cameras plus continuous analysis.",
        "limits": {
            "videos_per_month": 100,
            "analysis_minutes_per_month": 600,
            "streams": 5,
            "storage_gb": 50,
            "concurrent_jobs": 2,
        },
    },
    "enterprise": {
        "name": "Enterprise",
        "price_month_usd": 499,
        "blurb": "Multi-site, unlimited retention window.",
        "limits": {
            "videos_per_month": 10000,
            "analysis_minutes_per_month": 100000,
            "streams": 50,
            "storage_gb": 500,
            "concurrent_jobs": 8,
        },
    },
}

SETTING_SCHEMA: dict[str, dict[str, Any]] = {
    # Inference (applies to the next analysis run and to live view)
    "model": {"type": "string", "choices": MODEL_CHOICES, "validate": _choice(MODEL_CHOICES)},
    "confidence": {"type": "number", "validate": _number(0.05, 0.95)},
    "image_size": {"type": "integer", "validate": _number(320, 2560, int)},
    "frame_stride": {"type": "integer", "validate": _number(1, 30, int)},
    "device": {"type": "string", "choices": DEVICE_CHOICES, "validate": _choice(DEVICE_CHOICES)},
    "multiscale": {"type": "boolean", "validate": _flag},
    # Billing
    "plan": {"type": "string", "choices": list(PLANS), "validate": _choice(list(PLANS))},
    # Integrations
    "webhook_url": {"type": "string", "validate": _url},
    "webhook_secret": {"type": "string", "validate": _secret},
    "map_center": {"type": "array", "validate": _map_center},
    "map_style": {"type": "string", "validate": _url},
    "public_sources_enabled": {"type": "boolean", "validate": _flag},
}

DEFAULTS: dict[str, Any] = {
    "model": env_settings.model,
    "confidence": env_settings.confidence,
    "image_size": env_settings.image_size,
    "frame_stride": env_settings.frame_stride,
    "device": env_settings.device,
    "multiscale": env_settings.multiscale,
    "plan": "starter",
    "webhook_url": None,
    "webhook_secret": None,
    "map_center": None,
    "map_style": None,
    "public_sources_enabled": env_settings.auto_download_public_sources,
}


def get_all(db: Session) -> dict[str, Any]:
    """Every known key with its persisted value (falls back to the env default)."""
    stored = {row.key: _decode(row.value_json) for row in db.query(AppSetting).all()}
    return {key: stored.get(key, default) for key, default in DEFAULTS.items()}


def get(db: Session, key: str) -> Any:
    row = db.get(AppSetting, key)
    if row is not None:
        return _decode(row.value_json)
    return DEFAULTS.get(key)


def set_many(db: Session, values: dict[str, Any]) -> dict[str, Any]:
    """Validate and persist a partial settings patch. Raises ValueError on bad input."""
    cleaned: dict[str, Any] = {}
    for key, value in values.items():
        schema = SETTING_SCHEMA.get(key)
        if schema is None:
            raise ValueError(f"unknown setting: {key}")
        cleaned[key] = schema["validate"](value)
    for key, value in cleaned.items():
        row = db.get(AppSetting, key)
        payload = json.dumps(value)
        if row is None:
            db.add(AppSetting(key=key, value_json=payload))
        else:
            row.value_json = payload
    db.commit()
    return {**get_all(db), **cleaned}


def inference_config(db: Session) -> dict[str, Any]:
    """Model runtime values for the next job/live session (DB override, else env)."""
    values = get_all(db)
    return {
        "model": values["model"],
        "confidence": values["confidence"],
        "image_size": values["image_size"],
        "frame_stride": values["frame_stride"],
        "device": values["device"],
        "multiscale": values["multiscale"],
    }


def plan(name: str | None) -> dict[str, Any]:
    return PLANS.get(name or "starter", PLANS["starter"])


def _decode(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None
