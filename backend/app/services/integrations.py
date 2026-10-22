"""Outbound integrations: signed webhook delivery fired on completed/failed analysis jobs."""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from ..security import validate_external_url
from . import settings_store

ALLOWED_EVENTS = {"video.completed", "video.failed", "stream.overcrowding"}


def dispatch(db: Session, event: str, payload: dict) -> dict:
    """Best-effort POST to the configured webhook (SSRF-validated, 5s timeout, signed).

    Delivery failures are reported, never raised: webhooks must not break analysis.
    """
    if event not in ALLOWED_EVENTS:
        return {"delivered": False, "error": f"unknown event '{event}'"}
    url = settings_store.get(db, "webhook_url")
    if not url:
        return {"skipped": True, "reason": "no webhook configured"}
    try:
        url = validate_external_url(url, schemes={"http", "https"})
    except ValueError as exc:
        return {"delivered": False, "error": f"blocked: {exc}"}

    body = json.dumps(
        {"event": event, "sent_at": datetime.now(timezone.utc).isoformat(), "data": payload},
        separators=(",", ":"),
    ).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "ParkWiseAI/1.0",
        "X-Parkwise-Event": event,
    }
    secret = settings_store.get(db, "webhook_secret")
    if secret:
        headers["X-Parkwise-Signature"] = "sha256=" + hmac.new(
            secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()

    request = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310 - URL validated
            return {"delivered": response.status < 300, "status": response.status}
    except urllib.error.HTTPError as exc:
        return {"delivered": False, "status": exc.code, "error": str(exc)[:200]}
    except Exception as exc:  # DNS/connect/timeout errors
        return {"delivered": False, "error": str(exc)[:200]}


def notify_job(db: Session, job) -> dict:
    """Webhook helper used by the pipeline on completion/failure."""
    event = "video.completed" if job.status == "completed" else "video.failed"
    payload = {
        "id": job.id,
        "name": job.original_name,
        "status": job.status,
        "duration_seconds": job.duration_seconds,
        "max_vehicle_count": job.max_vehicle_count,
        "avg_confidence": job.avg_confidence,
        "model": job.model_name,
    }
    return dispatch(db, event, payload)
