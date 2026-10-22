"""Activity/audit trail (idea.md: privileged changes are recorded; dashboard shows 'what users do')."""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models import ActivityEvent


def record(
    db: Session,
    actor: str,
    action: str,
    object_type: str | None = None,
    object_id: str | None = None,
    detail: str | None = None,
) -> None:
    """Append one event and commit. Never raises for missing context fields."""
    try:
        db.add(
            ActivityEvent(
                actor=actor or "system",
                action=action[:48],
                object_type=object_type[:32] if object_type else None,
                object_id=str(object_id)[:64] if object_id else None,
                detail=(detail or "")[:2000] or None,
            )
        )
        db.commit()
    except Exception:  # pragma: no cover - audit writing must not break the action
        db.rollback()


def recent(db: Session, limit: int = 50) -> list[dict]:
    rows = (
        db.query(ActivityEvent)
        .order_by(ActivityEvent.created_at.desc(), ActivityEvent.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [
        {
            "id": row.id,
            "actor": row.actor,
            "action": row.action,
            "object_type": row.object_type,
            "object_id": row.object_id,
            "detail": row.detail,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }
        for row in rows
    ]


def breakdown(db: Session, days: int = 14) -> dict:
    """Action counts for the window plus per-day buckets (drives the dashboard bar chart)."""
    from datetime import datetime, timedelta, timezone

    start = datetime.now(timezone.utc) - timedelta(days=max(1, days))
    query = db.query(ActivityEvent).filter(ActivityEvent.created_at >= start)
    by_action: dict[str, int] = {}
    by_day: dict[str, dict[str, int]] = {}
    for row in query.all():
        by_action[row.action] = by_action.get(row.action, 0) + 1
        day = row.created_at.date().isoformat() if row.created_at else "unknown"
        bucket = by_day.setdefault(day, {})
        bucket[row.action] = bucket.get(row.action, 0) + 1
    total = db.query(func.count(ActivityEvent.id)).scalar() or 0
    return {"window_days": days, "total_events": int(total), "by_action": by_action, "by_day": by_day}
