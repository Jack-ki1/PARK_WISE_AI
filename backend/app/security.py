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
import socket
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import urlparse, urlunparse

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

# Literal metadata IPs (checked before generic link-local rules so the error names them).
METADATA_IPS = {"169.254.169.254", "100.100.100.200", "fd00:ec2::254"}

ALLOWED_STREAM_SCHEMES = {"rtsp", "rtsps", "http", "https", "tcp"}

# Only update last_login_at at most this often to avoid a write on every request.
LOGIN_TOUCH_SECONDS = 300


def hash_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _parse_trusted_cidrs(raw: str | None) -> list[ipaddress._BaseNetwork]:
    networks: list[ipaddress._BaseNetwork] = []
    for chunk in (raw or "").split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            networks.append(ipaddress.ip_network(chunk, strict=False))
        except ValueError:
            continue
    return networks


def _address_blocked(address: ipaddress._BaseAddress, allow_private: bool, trusted: list) -> str | None:
    """Return a reason string if this resolved address must be rejected, else None."""
    if str(address) in METADATA_IPS or (address.version == 6 and address.ipv4_mapped and str(address.ipv4_mapped) in METADATA_IPS):
        return f"metadata endpoint {address} is not allowed"
    if address.is_loopback:
        return f"loopback address {address} is not allowed"
    if address.is_link_local:
        return f"link-local address {address} is not allowed"
    if address.is_multicast:
        return f"multicast address {address} is not allowed"
    if address.is_unspecified:
        return f"unspecified address {address} is not allowed"
    if address.is_private or (address.version == 6 and address.is_site_local):
        if not allow_private:
            return f"private address {address} is not allowed in this context"
        if trusted and not any(address.version == net.version and address in net for net in trusted):
            return f"private address {address} is outside the trusted camera networks"
    return None


def validate_external_url(
    url: str,
    schemes: Iterable[str] | None = None,
    allow_private: bool = True,
    trusted_cidrs: str | None = None,
) -> str:
    """SSRF guard (API7). Returns the normalised URL or raises ValueError.

    Private/CGNAT ranges are allowed by default for CCTV cameras on LANs, but
    cloud metadata endpoints, loopback, link-local, multicast and unspecified
    addresses are always blocked. Every resolved address of a hostname is
    validated (DNS-rebinding defence). When ``trusted_cidrs`` (comma-separated)
    is provided and non-empty, private addresses must fall inside one of those
    networks; set ``allow_private=False`` to reject all private ranges (webhooks).
    """
    text = (url or "").strip()
    if not text or len(text) > 600:
        raise ValueError("URL is empty or too long")
    allowed = set(schemes) if schemes else ALLOWED_STREAM_SCHEMES
    parsed = urlparse(text)
    scheme = (parsed.scheme or "").lower()
    if scheme not in allowed:
        raise ValueError(f"unsupported scheme '{scheme}'; allowed: {', '.join(sorted(allowed))}")

    if parsed.username or parsed.password:
        raise ValueError("embedded credentials in URL are not allowed; this release stores no camera credentials — use a credential-free URL or an authenticated proxy")

    host = (parsed.hostname or "").lower()
    if not host:
        raise ValueError("URL must include a host")
    if host in BLOCKED_HOSTS or host.endswith(".internal"):
        raise ValueError("host is not allowed")

    trusted = _parse_trusted_cidrs(trusted_cidrs if trusted_cidrs is not None else env_settings.trusted_camera_cidrs)

    def _check(address: ipaddress._BaseAddress) -> None:
        reason = _address_blocked(address, allow_private, trusted)
        if reason:
            raise ValueError(reason)

    # Literal IP host: validate directly.
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if literal.version == 6 and literal.ipv4_mapped is not None:
            _check(literal.ipv4_mapped)
        else:
            _check(literal)
        return text

    # Hostname: resolve and validate ALL resolved addresses (DNS rebinding defence).
    try:
        addr_infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"host '{host}' could not be resolved ({exc.errno})") from None
    resolved = list({info[4][0] for info in addr_infos})
    if not resolved:
        raise ValueError(f"host '{host}' resolved to no addresses")
    for addr_str in resolved:
        try:
            address = ipaddress.ip_address(addr_str)
        except ValueError:
            continue
        if address.version == 6 and address.ipv4_mapped is not None:
            _check(address.ipv4_mapped)
        else:
            _check(address)

    return text


def redact_url(url: str | None) -> str | None:
    """Return a display-safe URL with any userinfo stripped; None on parse failure."""
    if not url:
        return url
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            host = parsed.hostname
            if parsed.port:
                host = f"{host}:{parsed.port}"
            return urlunparse((parsed.scheme, host, parsed.path, parsed.params, parsed.query, ""))
        return url
    except Exception:
        return None


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
    (where FastAPI does not provide a Request); WS auth uses short-lived tickets.
    """
    raw = authorization or x_api_key
    user = authenticate(db, raw)
    if user is None:
        if env_settings.auth_required:
            raise HTTPException(status_code=401, detail="A valid API key is required")
        return None
    # Throttle the last-login write so it does not fire on every request (write contention).
    now = datetime.now(timezone.utc)
    previous = user.last_login_at
    if previous is not None and previous.tzinfo is None:
        previous = previous.replace(tzinfo=timezone.utc)
    if previous is None or (now - previous).total_seconds() >= LOGIN_TOUCH_SECONDS:
        user.last_login_at = now
        db.commit()
    return user


def require_roles(user: User | None, roles: Iterable[str]) -> None:
    """Function-level authorisation (API5).

    - When a user identity is present (valid API key), their role is always
      enforced, even in development mode: identifying yourself must not weaken
      checks. Admin always passes.
    - When no identity is present: allowed only if auth is disabled (local
      development); with auth enabled this is a 401.
    """
    if user is not None:
        if user.role == "admin":
            return
        if user.role not in set(roles):
            raise HTTPException(status_code=403, detail=f"Requires one of: {', '.join(roles)}")
        return
    if env_settings.auth_required:
        raise HTTPException(status_code=401, detail="A valid API key is required")


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
