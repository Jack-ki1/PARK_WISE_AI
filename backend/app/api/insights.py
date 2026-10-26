"""Dashboard analytics: Power-BI-style KPIs, chart series and activity breakdowns."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import Integer, func
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import ActivityEvent, DetectionSample, OccupancySample, ParkingSpace, Stream, VideoJob
from ..security import current_user
from ..services import activity, billing

router = APIRouter(prefix="/api", dependencies=[Depends(current_user)])


@router.get("/dashboard/analytics")
def dashboard_analytics(db: Session = Depends(get_db)) -> dict:
    """Everything the Dashboard screen needs in one round trip."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    day_window = (now - timedelta(days=13)).date()

    totals = {
        "videos_total": db.query(func.count(VideoJob.id)).scalar() or 0,
        "videos_completed": db.query(func.count(VideoJob.id))
        .filter(VideoJob.status == "completed")
        .scalar()
        or 0,
        "videos_processing": db.query(func.count(VideoJob.id))
        .filter(VideoJob.status.in_(["queued", "processing"]))
        .scalar()
        or 0,
        "videos_failed": db.query(func.count(VideoJob.id)).filter(VideoJob.status == "failed").scalar()
        or 0,
        "bays_configured": db.query(func.count(ParkingSpace.id)).scalar() or 0,
        "detections_logged": db.query(func.count(DetectionSample.id)).scalar() or 0,
        "streams_total": db.query(func.count(Stream.id)).scalar() or 0,
        "streams_live": db.query(func.count(Stream.id)).filter(Stream.status == "live").scalar() or 0,
        "videos_this_month": db.query(func.count(VideoJob.id))
        .filter(VideoJob.created_at >= month_start)
        .scalar()
        or 0,
    }

    duration = (
        db.query(func.coalesce(func.sum(VideoJob.duration_seconds), 0.0))
        .filter(VideoJob.status == "completed")
        .scalar()
        or 0.0
    )
    peak = db.query(func.max(VideoJob.max_vehicle_count)).filter(VideoJob.status == "completed").scalar()
    avg_conf = db.query(func.avg(VideoJob.avg_confidence)).filter(VideoJob.status == "completed").scalar()

    # Occupancy / utilisation across every reviewed video -------------------
    state_rows = (
        db.query(OccupancySample.state, func.count(OccupancySample.id))
        .group_by(OccupancySample.state)
        .all()
    )
    state_mix = [{"state": state, "samples": int(count)} for state, count in state_rows]
    occupied_samples = next((row["samples"] for row in state_mix if row["state"] == "occupied"), 0)
    free_samples = next((row["samples"] for row in state_mix if row["state"] == "free"), 0)
    observed = occupied_samples + free_samples
    utilisation_percent = round(occupied_samples / observed * 100, 1) if observed else None

    per_video = (
        db.query(
            VideoJob.id,
            VideoJob.original_name,
            VideoJob.completed_at,
            VideoJob.max_vehicle_count,
            VideoJob.avg_confidence,
            VideoJob.duration_seconds,
            func.count(OccupancySample.id).label("samples"),
            func.sum((OccupancySample.state == "occupied").cast(Integer)).label("occupied"),
            func.sum((OccupancySample.state == "free").cast(Integer)).label("free"),
        )
        .outerjoin(OccupancySample, OccupancySample.video_id == VideoJob.id)
        .filter(VideoJob.status == "completed")
        .group_by(VideoJob.id)
        .all()
    )
    trend_by_day: dict[str, list[float]] = {}
    reviewed: list[dict] = []
    for row in per_video:
        samples = int(row.samples or 0)
        occupied = int(row.occupied or 0)
        free = int(row.free or 0)
        # Only use observed states (occupied + free) as denominator, exclude unknown
        observed = occupied + free
        percent = round(occupied / observed * 100, 1) if observed > 0 else None
        day = row.completed_at.date().isoformat() if row.completed_at else "unknown"
        if percent is not None:
            trend_by_day.setdefault(day, []).append(percent)
        reviewed.append(
            {
                "id": row.id,
                "name": row.original_name,
                "completed_at": row.completed_at.isoformat() if row.completed_at else None,
                "peak_vehicles": row.max_vehicle_count,
                # Handle 0.0 confidence correctly - don't convert to None
                "avg_confidence": round(float(row.avg_confidence), 3) if row.avg_confidence is not None else None,
                "duration_seconds": row.duration_seconds,
                "samples": samples,
                "occupied_share_percent": percent,
            }
        )
    trend = [
        {"date": day, "percent": round(sum(values) / len(values), 1)}
        for day, values in sorted(trend_by_day.items())
    ]

    # Activity: what users have been doing (uploads / runs / deletes / edits)
    activity_start = datetime.combine(day_window, datetime.min.time(), tzinfo=timezone.utc)
    action_rows = (
        db.query(ActivityEvent.action, func.count(ActivityEvent.id))
        .filter(ActivityEvent.created_at >= activity_start)
        .group_by(ActivityEvent.action)
        .all()
    )
    by_action = {action: int(count) for action, count in action_rows}
    day_rows = (
        db.query(func.date(ActivityEvent.created_at), ActivityEvent.action, func.count(ActivityEvent.id))
        .filter(ActivityEvent.created_at >= activity_start)
        .group_by(func.date(ActivityEvent.created_at), ActivityEvent.action)
        .all()
    )
    by_day: dict[str, dict[str, int]] = {}
    for day_value, action, count in day_rows:
        key = str(day_value)
        by_day.setdefault(key, {})[action] = int(count)
    activity_days = [{"date": (day_window + timedelta(days=offset)).isoformat()} for offset in range(14)]
    for entry in activity_days:
        entry["actions"] = by_day.get(entry["date"], {})
        entry["total"] = sum(entry["actions"].values())

    status_rows = db.query(VideoJob.status, func.count(VideoJob.id)).group_by(VideoJob.status).all()
    status_breakdown = [{"status": status, "count": int(count)} for status, count in status_rows]

    top_videos = sorted(reviewed, key=lambda item: item["peak_vehicles"] or 0, reverse=True)[:6]
    usage = billing.usage(db)

    return {
        "generated_at": now.isoformat(),
        "kpis": {
            **totals,
            "analyzed_hours": round(duration / 3600.0, 2),
            "peak_vehicles": int(peak) if peak is not None else None,
            "avg_confidence": round(float(avg_conf), 3) if avg_conf is not None else None,
            "utilisation_percent": utilisation_percent,
            "storage_gb": round(usage["storage_bytes"] / (1024**3), 2),
            "concurrent_jobs": usage["concurrent_jobs"],
        },
        "charts": {
            "occupancy_trend": trend,
            "activity_by_day": activity_days,
            "activity_by_action": by_action,
            "status_breakdown": status_breakdown,
            "state_mix": state_mix,
            "utilisation": [
                {"label": "Occupied samples", "value": occupied_samples},
                {"label": "Free samples", "value": free_samples},
                {
                    "label": "Unobserved bays",
                    "value": next(
                        (row["samples"] for row in state_mix if row["state"] == "unknown"), 0
                    ),
                },
            ],
            "top_videos": top_videos,
        },
        "reviewed_videos": sorted(
            reviewed, key=lambda item: item["completed_at"] or "", reverse=True
        ),
    }


@router.get("/activity")
def activity_feed(limit: int = 50, db: Session = Depends(get_db)) -> dict:
    return {"items": activity.recent(db, limit)}
