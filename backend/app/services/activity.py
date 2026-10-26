"""Activity/audit trail (idea.md: privileged changes are recorded; dashboard shows 'what users do')."""

from __future__ import annotations

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
