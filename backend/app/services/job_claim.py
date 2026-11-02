"""One-writer leases for video analysis jobs.

Two things this protects against:

* **Double processing.** A check-then-set on ``job.status`` lets two requests (or a
  restart plus a retry) both start work on one job; their writers overwrite each
  other's output and the plan's ``concurrent_jobs`` quota silently overruns. Claiming
  is a single conditional UPDATE, so exactly one caller sees ``rowcount == 1``.
* **Jobs stuck forever.** A worker that dies mid-run leaves a ``processing`` row that
  blocks reprocessing, deletion and calibration, and counts against the quota for the
  rest of the month. A lease with an expiry makes that state detectable: the sweeper
  turns it into an honest ``failed`` row the operator can re-run.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models import VideoJob

# A running job must extend its lease this often; a job that stops doing so is dead.
LEASE_SECONDS = 180
# A queued job whose background task never started (crash between commit and handoff)
# is abandoned after this long.
QUEUED_TIMEOUT_SECONDS = 900

_ABANDONED = "Analysis stopped unexpectedly (worker lease expired). Re-run the analysis."
_NEVER_STARTED = "Analysis never started (server restarted before the job began). Re-run the analysis."


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(db: Session, video_id: str, *, terminal_statuses: tuple[str, ...] = ("uploaded", "completed", "failed")) -> bool:
    """Move a job into ``queued`` iff it is not already queued or processing.

    The conditional UPDATE is what makes two simultaneous "Run analysis" clicks return
    one 202 and one 409 instead of both handing work to the pipeline.
    """
    now = utcnow()
    updated = (
        db.query(VideoJob)
        .filter(VideoJob.id == video_id, VideoJob.status.in_(list(terminal_statuses)))
        .update(
            {
                "status": "queued",
                "progress_percent": 0.0,
                "current_frame": 0,
                "processed_frames": 0,
                "chunk_cursor_frame": 0,
                "max_vehicle_count": None,
                "avg_confidence": None,
                "confidence_sample_count": 0,
                "confidence_total": 0.0,
                "error_message": None,
                "processed_video_path": None,
                "completed_at": None,
                # Queue clock: reap_stale() needs to know when a queued job was asked
                # for, which is not the same as when the row was uploaded.
                "started_at": now,
            },
            synchronize_session=False,
        )
    )
    if updated == 1:
        db.commit()
    else:
        db.rollback()
    return updated == 1


def claim(
    db: Session,
    video_id: str,
    *,
    from_statuses: tuple[str, ...] = ("queued",),
    lease_seconds: int = LEASE_SECONDS,
    owner: str | None = None,
    reset_cursor: bool = True,
) -> bool:
    """Move a job into ``processing`` iff it is currently in ``from_statuses``.

    True means this caller owns the job (and its lease); False means somebody else
    already claimed it, so the caller must do nothing.
    """
    now = utcnow()
    values = {
        "status": "processing",
        "lease_owner": owner or f"worker:{uuid.uuid4().hex[:12]}",
        "lease_expires_at": now + timedelta(seconds=lease_seconds),
        "attempt_count": VideoJob.attempt_count + 1,
        "error_message": None,
        "started_at": now,
    }
    if reset_cursor:
        values["chunk_cursor_frame"] = 0
    statement = (
        db.query(VideoJob)
        .filter(VideoJob.id == video_id, VideoJob.status.in_(list(from_statuses)))
        .update(values, synchronize_session=False)
    )
    claimed = statement == 1
    if claimed:
        db.commit()
    else:
        db.rollback()
    return claimed


def heartbeat(db: Session, video_id: str, owner: str, *, lease_seconds: int = LEASE_SECONDS) -> bool:
    """Extend the lease. False means ownership was lost (taken over or reaped)."""
    updated = (
        db.query(VideoJob)
        .filter(VideoJob.id == video_id, VideoJob.lease_owner == owner, VideoJob.status == "processing")
        .update(
            {"lease_expires_at": utcnow() + timedelta(seconds=lease_seconds)},
            synchronize_session=False,
        )
    )
    db.commit()
    return updated == 1


def release(db: Session, video_id: str, owner: str) -> None:
    """Drop the lease once the job reached a terminal state."""
    db.query(VideoJob).filter(VideoJob.id == video_id, VideoJob.lease_owner == owner).update(
        {"lease_owner": None, "lease_expires_at": None}, synchronize_session=False
    )
    db.commit()


def reap_stale(db: Session, *, startup: bool = False) -> dict[str, int]:
    """Fail jobs that can no longer complete, so they stop blocking the operator.

    Covers three stuck shapes:

    * ``processing`` with an expired lease (worker died mid-run),
    * ``processing`` with no lease at all (rows written before leases existed),
    * ``queued`` past the handoff timeout — or, when ``startup=True``, *any*
      queued row: a restart kills every in-process background task, so nothing
      will ever claim them again and they would 409 reprocess/delete/calibration
      (and hold the plan's concurrency slot) until the timeout elapsed.

    Called at startup, and from the dashboard poll endpoints as a runtime
    backstop so a stuck row clears within its timeout without another restart.
    Single-process deployment is assumed for the startup sweep — tickets and
    stream sessions are in-memory, so multiple workers are unsupported anyway.
    """
    now = utcnow()
    reaped_leases = (
        db.query(VideoJob)
        .filter(
            VideoJob.status == "processing",
            or_(VideoJob.lease_expires_at < now, VideoJob.lease_expires_at.is_(None)),
        )
        .update({"status": "failed", "error_message": _ABANDONED, "completed_at": now, "lease_owner": None}, synchronize_session=False)
    )
    if startup:
        reaped_queued = (
            db.query(VideoJob)
            .filter(VideoJob.status == "queued")
            .update({"status": "failed", "error_message": _NEVER_STARTED, "completed_at": now}, synchronize_session=False)
        )
    else:
        reaped_queued = (
            db.query(VideoJob)
            .filter(
                VideoJob.status == "queued",
                or_(
                    VideoJob.started_at < now - timedelta(seconds=QUEUED_TIMEOUT_SECONDS),
                    VideoJob.started_at.is_(None) & (VideoJob.created_at < now - timedelta(seconds=QUEUED_TIMEOUT_SECONDS)),
                ),
            )
            .update({"status": "failed", "error_message": _NEVER_STARTED, "completed_at": now}, synchronize_session=False)
        )
    db.commit()
    return {"expired_leases": int(reaped_leases), "abandoned_queue": int(reaped_queued)}
