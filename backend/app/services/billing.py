"""Plan/usage metering and quota enforcement (billing tab + API4-style resource guards)."""

from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import settings as env_settings
from ..models import Stream, VideoJob
from . import settings_store


def _month_start() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def storage_bytes(db: Session) -> int:
    root = Path(env_settings.data_dir).expanduser().resolve()
    total = 0
    for folder in ("uploads", "processed", "previews", "streams"):
        base = root / folder
        if not base.exists():
            continue
        for path in base.iterdir():
            try:
                if path.is_file():
                    total += os.stat(path).st_size
            except OSError:
                continue
    return total


def usage(db: Session) -> dict:
    start = _month_start()
    videos_month = (
        db.query(func.count(VideoJob.id)).filter(VideoJob.created_at >= start).scalar() or 0
    )
    minutes_row = (
        db.query(func.coalesce(func.sum(VideoJob.duration_seconds), 0.0))
        .filter(VideoJob.created_at >= start, VideoJob.status == "completed")
        .scalar()
        or 0.0
    )
    concurrent = (
        db.query(func.count(VideoJob.id))
        .filter(VideoJob.status.in_(["queued", "processing"]))
        .scalar()
        or 0
    )
    streams = db.query(func.count(Stream.id)).scalar() or 0
    return {
        "videos_this_month": int(videos_month),
        "analysis_minutes_this_month": round(float(minutes_row), 1),
        "storage_bytes": storage_bytes(db),
        "concurrent_jobs": int(concurrent),
        "streams": int(streams),
    }


def billing_report(db: Session) -> dict:
    plan_name = settings_store.get(db, "plan")
    plan = settings_store.plan(plan_name)
    used = usage(db)
    limits = plan["limits"]
    storage_gb = used["storage_bytes"] / (1024**3)
    meters = [
        ("Videos uploaded", used["videos_this_month"], limits["videos_per_month"], "videos_per_month"),
        (
            "Analysis minutes",
            used["analysis_minutes_this_month"],
            limits["analysis_minutes_per_month"],
            "analysis_minutes_per_month",
        ),
        ("Camera streams", used["streams"], limits["streams"], "streams"),
        ("Concurrent jobs", used["concurrent_jobs"], limits["concurrent_jobs"], "concurrent_jobs"),
        ("Storage (GB)", round(storage_gb, 2), limits["storage_gb"], "storage_gb"),
    ]
    return {
        "plan": plan_name,
        "plan_info": plan,
        # Honest labelling: no payment processor is connected in this build.
        "billing_mode": "local_simulation",
        "billing_note": (
            "Illustrative local plan configuration for a self-hosted pilot. "
            "No payment processor is connected and no charges are made."
        ),
        "usage": {
            **used,
            "storage_gb": round(storage_gb, 2),
        },
        "meters": [
            {
                "label": label,
                "used": used_value,
                "limit": limit_value,
                "key": key,
                "percent": (round(used_value / limit_value * 100, 1) if limit_value else 0),
                "exceeded": bool(limit_value is not None and used_value > limit_value),
            }
            for label, used_value, limit_value, key in meters
        ],
    }


def _over(plan_limits: dict, key: str, value) -> str | None:
    """Enforcement helper: block when the meter has reached (or passed) its limit."""
    limit = plan_limits.get(key)
    if limit is None or value < limit:
        return None
    label = key.replace("_per_month", "").replace("_", " ")
    return f"Plan limit reached for {label} ({value}/{limit}). Upgrade the plan in Reports & Settings."


def check_can_upload(db: Session) -> None:
    plan = settings_store.plan(settings_store.get(db, "plan"))
    start = _month_start()
    count = (
        db.query(func.count(VideoJob.id)).filter(VideoJob.created_at >= start).scalar() or 0
    )
    message = _over(plan["limits"], "videos_per_month", int(count))
    if message:
        raise HTTPException(status_code=402, detail=message)


def check_can_process(db: Session) -> None:
    plan = settings_store.plan(settings_store.get(db, "plan"))
    concurrent = (
        db.query(func.count(VideoJob.id))
        .filter(VideoJob.status.in_(["queued", "processing"]))
        .scalar()
        or 0
    )
    message = _over(plan["limits"], "concurrent_jobs", int(concurrent))
    if message:
        raise HTTPException(status_code=402, detail=message)


def check_can_add_stream(db: Session) -> None:
    plan = settings_store.plan(settings_store.get(db, "plan"))
    count = db.query(func.count(Stream.id)).scalar() or 0
    message = _over(plan["limits"], "streams", int(count))
    if message:
        raise HTTPException(status_code=402, detail=message)
