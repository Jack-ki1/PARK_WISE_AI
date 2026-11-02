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

Deployment note: the store is an in-process dict (lock-protected, so redemption
is single-use across the threadpool), which assumes a **single worker process**.
That matches the rest of the runtime — stream sessions and rate-limit buckets
are also in-memory — so ``uvicorn --workers N`` or horizontally scaled replicas
are unsupported until this store (and those) move to shared state.
"""

from __future__ import annotations

import secrets
import threading
import time
from typing import Dict

TTL_SECONDS = 60
MAX_TICKETS = 1000

# {ticket: {"kind": str, "object_id": str, "expires_at": float}}
_tickets: Dict[str, dict] = {}
# Ticket redemption runs on the threadpool (one thread per WebSocket handshake), so
# the check-and-consume below must not interleave — without this lock two simultaneous
# redemptions of one ticket both see it present and both pass.
_lock = threading.Lock()


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
    with _lock:
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
    if not ticket:
        return False
    with _lock:
        # pop() is the consume: whoever takes it owns it, exactly once.
        data = _tickets.pop(ticket, None)
        if data is None:
            return False
        if time.time() > data["expires_at"]:
            return False
        if data["kind"] != kind or data["object_id"] != str(object_id):
            # Not ours; put it back so its real holder can redeem it.
            _tickets[ticket] = data
            return False
    return True


def clear() -> None:
    with _lock:
        _tickets.clear()
