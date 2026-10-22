"""Security helpers mapped to the OWASP API Security Top 10 (2023).

- API2/API5: optional bearer API-key auth with role gates (admin/operator/viewer).
- API1: object ownership is enforced by loading the object through route-scoped
  dependencies (see routes) rather than trusting client ids blindly.
- API3: every response is shaped by Pydantic response models; settings writes go
  through an allow-list schema (settings_store.SETTING_SCHEMA).
- API4: a per-client rate limiter for mutating requests (config.py rate_limit_per_minute).
- API7: SSRF validation for user-supplied stream/webhook URLs (schemes, metadata hosts).
"""

from __future__ import annotations

import hashlib
import ipaddress
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from .config import settings as env_settings
from .database import get_db
from .models import User

ROLES = ("admin", "operator", "viewer")

# Hostnames that must never be fetched server-side (cloud metadata / link-local).
BLOCKED_HOSTS = {
    "metadata.google.internal",
    "metadata.goog",
    "metadata",
    "instance-data",
}

ALLOWED_STREAM_SCHEMES = {"rtsp", "rtsps", "http", "https", "tcp"}


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def validate_external_url(url: str, schemes: Iterable[str] | None = None) -> str:
    """SSRF guard (API7). Returns the normalised URL or raises ValueError.

    Private/CGNAT ranges are deliberately allowed: real CCTV cameras live on LAN
    addresses, which is the whole point of the live view. Cloud metadata endpoints
    (169.254.0.0/16, link-local, hostnames above, non-http(s)/rtsp schemes) are blocked.
    """
    text = (url or "").strip()
    if not text or len(text) > 600:
        raise ValueError("URL is empty or too long")
    allowed = set(schemes) if schemes else ALLOWED_STREAM_SCHEMES
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in allowed:
        raise ValueError(f"unsupported scheme '{scheme}'; allowed: {', '.join(sorted(allowed))}")
    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL must include a host")
    if host in BLOCKED_HOSTS or host.endswith(".internal"):
        raise ValueError("host is not allowed")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None:
        if address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified:
            raise ValueError("address is not allowed")
        if address.version == 6 and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
            if address.is_link_local:
                raise ValueError("address is not allowed")
    if scheme in {"http", "https"}:
        # Only enforce http(s) metadata rules; rtsp://169.254.x.x is still blocked above.
        if host in {"169.254.169.254", "100.100.100.200"}:
            raise ValueError("metadata endpoints are not allowed")
    return text


def authenticate(db: Session, raw_key: str | None) -> User | None:
    if not raw_key:
        return None
    token = raw_key.removeprefix("Bearer ").strip()
    if not token:
        return None
    user = db.query(User).filter(User.api_key_hash == hash_key(token)).first()
    if user is None or not user.is_active:
        return None
    return user


def current_user(
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> User | None:
    """Resolve the caller. Returns None when auth is disabled, a User when a key is sent.

    When PARKWISE_AUTH_REQUIRED=true a valid key is mandatory (API2). Request is
    deliberately not injected here so the same dependency runs on WebSocket routes
    (where FastAPI does not provide a Request); WS token auth uses ?key= instead.
    """
    raw = authorization or x_api_key
    user = authenticate(db, raw)
    if user is None:
        if env_settings.auth_required:
            raise HTTPException(status_code=401, detail="A valid API key is required")
        return None
    user.last_login_at = datetime.now(timezone.utc)
    db.commit()
    return user


def require_roles(user: User | None, roles: Iterable[str]) -> None:
    """Function-level authorisation (API5). Admin always passes."""
    if not env_settings.auth_required:
        return
    if user is None:
        raise HTTPException(status_code=401, detail="A valid API key is required")
    if user.role == "admin":
        return
    if user.role not in set(roles):
        raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")


def actor_name(user: User | None) -> str:
    return user.username if user else "operator"


class RateLimiter:
    """Fixed-window per-client limiter for mutating requests (API4/API6)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - window_seconds
            bucket[:] = [stamp for stamp in bucket if stamp > cutoff]
            if len(bucket) >= limit:
                retry = window_seconds - int(now - bucket[0])
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded ({limit}/min); retry in {max(retry, 1)}s",
                    headers={"Retry-After": str(max(retry, 1))},
                )
            bucket.append(now)
            if len(self._hits) > 512:  # keep memory bounded
                for stale in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                    self._hits.pop(stale, None)


rate_limiter = RateLimiter()


def rate_limit(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Dependency for mutating endpoints; buckets keyed by API key when sent, else IP."""
    limit = env_settings.rate_limit_per_minute
    if limit <= 0:
        return
    raw = authorization or x_api_key
    if raw:
        identity = "key:" + hash_key(raw)[:16]
    else:
        identity = "ip:" + (request.client.host if request.client else "anonymous")
    rate_limiter.check(identity, limit)
