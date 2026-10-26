"""Short-lived, single-use WebSocket tickets.

Browsers cannot attach an ``X-API-Key`` header to a WebSocket handshake, so a
durable API key must never be put in the URL (it would leak through logs,
proxies and browser history). Instead the caller exchanges its credentials for
a ticket that is:

- bound to one kind of object (``stream`` / ``video``) and one id,
- valid for 60 seconds,
- consumed on the first successful validation.

Used by ``/api/ws/streams/{id}`` (live frames) and ``/api/ws/videos/{id}``
(job progress).
"""

from __future__ import annotations

import secrets
import time
from typing import Dict

TTL_SECONDS = 60
MAX_TICKETS = 1000

# {ticket: {"kind": str, "object_id": str, "expires_at": float}}
_tickets: Dict[str, dict] = {}


def _purge_expired() -> None:
    """Drop expired tickets (called on every mint so the store cannot grow stale)."""
    now = time.time()
    expired = [key for key, data in _tickets.items() if now > data["expires_at"]]
    for key in expired:
        del _tickets[key]
    if len(_tickets) <= MAX_TICKETS:
        return
    oldest = sorted(_tickets.keys(), key=lambda k: _tickets[k]["expires_at"])
    for key in oldest[: len(_tickets) - MAX_TICKETS]:
        del _tickets[key]


def create_ticket(kind: str, object_id: str) -> str:
    _purge_expired()
    ticket = f"ws_{secrets.token_urlsafe(32)}"
    _tickets[ticket] = {"kind": kind, "object_id": str(object_id), "expires_at": time.time() + TTL_SECONDS}
    return ticket


def validate_ticket(ticket: str | None, kind: str, object_id: str) -> bool:
    """True when the ticket exists, is fresh, matches the object and is unused.

    A valid ticket is always consumed; an expired one is removed. A ticket for a
    different object is refused but left in the store (it may still be redeemed
    against the object it was minted for).
    """
    if not ticket or ticket not in _tickets:
        return False
    data = _tickets[ticket]
    if time.time() > data["expires_at"]:
        del _tickets[ticket]
        return False
    if data["kind"] != kind or data["object_id"] != str(object_id):
        return False
    del _tickets[ticket]
    return True


def clear() -> None:
    _tickets.clear()
