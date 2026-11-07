"""Security helpers mapped to the OWASP API Security Top 10 (2023).

- API2/API5: optional bearer API-key auth with role gates (admin/operator/viewer).
- API1: object ownership is enforced by loading the object through route-scoped
  dependencies (see routes) rather than trusting client ids blindly.
- API3: the core read/write endpoints declare Pydantic response models, and
  settings writes go through an allow-list schema (settings_store.SETTING_SCHEMA);
  the remaining endpoints return explicitly constructed, schema-checked dicts.
- API4: a per-client rate limiter for mutating requests (config.py rate_limit_per_minute).
- API7: SSRF validation for user-supplied stream/webhook URLs (schemes, metadata hosts).
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
import secrets
import socket
import threading
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Iterable
from urllib.parse import parse_qsl, urlparse, urlunparse

from fastapi import Depends, Header, HTTPException, Query, Request
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
    if address.is_reserved:
        # Includes the IPv4 limited broadcast (255.255.255.255) and 240/4 — a
        # target nobody legitimately points a camera or webhook at.
        return f"reserved address {address} is not allowed"
    if address.version == 4 and str(address).endswith(".255"):
        # Directed broadcast of the common /24 LAN. A host that claims the
        # subnet's broadcast address is a misconfiguration, and broadcast
        # amplification is never a valid stream/webhook target.
        return f"broadcast address {address} is not allowed"
    if address.is_private or (address.version == 6 and address.is_site_local):
        if not allow_private:
            return f"private address {address} is not allowed in this context"
        if trusted and not any(address.version == net.version and address in net for net in trusted):
            return f"private address {address} is outside the trusted camera networks"
    return None


def _validate_and_resolve(
    url: str,
    schemes: Iterable[str] | None,
    allow_private: bool,
    trusted_cidrs: str | None,
) -> tuple[str, list[str]]:
    """Shared SSRF check: returns (normalised URL, every validated address).

    The resolved list comes back so a caller can connect to *these* addresses
    instead of resolving the hostname again — that second lookup is the gap DNS
    rebinding used to slip through.
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
        return text, [str(literal)]

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

    return text, resolved


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
    text, _ = _validate_and_resolve(url, schemes, allow_private, trusted_cidrs)
    return text


def pin_validated_url(
    url: str,
    schemes: Iterable[str] | None = None,
    allow_private: bool = True,
    trusted_cidrs: str | None = None,
    pin_schemes: Iterable[str] | None = None,
) -> tuple[str, str | None]:
    """Validate a URL and return (address-pinned URL, original hostname).

    Closing the DNS-rebinding window means connecting to the address that was
    actually validated, not to the hostname (which the HTTP client would resolve a
    second time, potentially to an internal target). By default only plain HTTP is
    pinned: HTTPS must keep the hostname in the URL and the TLS handshake, because
    connecting by address breaks certificate validation — and there the
    certificate is the check that matters. ``pin_schemes`` widens (or narrows)
    that set — e.g. camera captures pass ``{"http", "rtsp", "tcp"}``, schemes
    whose clients do no trustworthy certificate validation anyway. Returns
    ``(url, None)`` when pinning does not apply.
    """
    text, resolved = _validate_and_resolve(url, schemes, allow_private, trusted_cidrs)
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    try:
        ipaddress.ip_address(host)
        return text, None  # already an address literal
    except ValueError:
        pass
    to_pin = set(pin_schemes) if pin_schemes is not None else {"http"}
    if parsed.scheme not in to_pin or not resolved:
        return text, None
    address = ipaddress.ip_address(resolved[0])
    netloc = f"[{address}]" if address.version == 6 else str(address)
    if parsed.port:
        netloc = f"{netloc}:{parsed.port}"
    return urlunparse(parsed._replace(netloc=netloc)), host


def redact_url(url: str | None) -> str | None:
    """Return a display-safe URL: userinfo stripped, query values masked, no fragment.

    Only this redacted form is ever sent to clients; the full URL stays in the
    database. Query strings used to survive verbatim, which leaked camera tokens
    (``?token=…``) into list responses — values are now replaced with ``***``
    while keys and structure are kept so the display stays recognizable.
    """
    if not url:
        return url
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.hostname:
            return None
        host = parsed.hostname
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        if parsed.port:
            host = f"{host}:{parsed.port}"
        masked_query = ""
        if parsed.query:
            masked_query = "&".join(f"{key}=***" for key, _ in parse_qsl(parsed.query, keep_blank_values=True))
        return urlunparse((parsed.scheme, host, parsed.path, parsed.params, masked_query, ""))
    except Exception:
        return None


# Absolute POSIX/Windows paths embedded in exception text (FileNotFoundError,
# OpenCV/ffmpeg messages, tracebacks converted to strings …). Viewers must never
# learn the server's filesystem layout from a job's error banner.
_PATH_PATTERN = re.compile(r"(?:[A-Za-z]:\\[^\s\"']+)|(?:/(?:[\w.\-]+/)+[\w.\-]+)")


def sanitize_error_message(exc: BaseException, *, limit: int = 300) -> str:
    """One-line, path-free ``"ExcType: message"`` safe to return to any viewer.

    The full exception text stays in the server log (callers pair this with
    ``logger.exception``). Newlines collapse, filesystem paths are masked, and
    the result is truncated so an error banner cannot carry a dump.
    """
    name = type(exc).__name__
    text = " ".join(str(exc).split())
    text = _PATH_PATTERN.sub("[path]", text)
    if not text:
        text = "unexpected error"
    return f"{name}: {text}"[:limit]


def authenticate(db: Session, raw_key: str | None) -> User | None:
    if not raw_key:
        return None
    # RFC 7235 auth-scheme names are case-insensitive: "bearer pk_…" must work.
    parts = raw_key.split(None, 1)
    token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else raw_key.strip()
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
    """Sliding-window per-client limiter for mutating requests (API4/API6)."""

    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def try_consume(self, key: str, limit: int, window_seconds: int = 60) -> tuple[bool, int]:
        """Record one hit. Returns (allowed, seconds_until_the_window_opens_up)."""
        if limit <= 0:
            return True, 0
        now = time.monotonic()
        with self._lock:
            bucket = self._hits[key]
            cutoff = now - window_seconds
            bucket[:] = [stamp for stamp in bucket if stamp > cutoff]
            if len(bucket) >= limit:
                retry = window_seconds - int(now - bucket[0])
                return False, max(retry, 1)
            bucket.append(now)
            if len(self._hits) > 512:  # keep memory bounded
                for stale in [k for k, v in self._hits.items() if not v or v[-1] < cutoff]:
                    self._hits.pop(stale, None)
                if len(self._hits) > 512:
                    # Expired-bucket cleanup alone cannot bound a flood of *fresh*
                    # unique keys, so drop the least-recently used ones too. Losing
                    # a bucket only grants that client a fresh window — it cannot
                    # grow memory past the cap.
                    overflow = len(self._hits) - 512
                    coldest = sorted(self._hits, key=lambda k: self._hits[k][-1])[:overflow]
                    for key_to_drop in coldest:
                        self._hits.pop(key_to_drop, None)
        return True, 0

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        allowed, retry = self.try_consume(key, limit, window_seconds)
        if not allowed:
            raise HTTPException(
                status_code=429,
                detail=f"Rate limit exceeded ({limit}/min); retry in {retry}s",
                headers={"Retry-After": str(retry)},
            )


rate_limiter = RateLimiter()
# Key-bruteforce guard: authenticate() hits the DB on every guess, so failed
# attempts get their own much tighter budget than ordinary API traffic.
auth_limiter = RateLimiter()
AUTH_LIMIT_PER_MINUTE = 30


def client_identity(request: Request, authorization: str | None = None, x_api_key: str | None = None) -> str:
    """Rate-limit bucket key: API key when presented, otherwise the client address.

    Behind a reverse proxy every request arrives from the proxy's address, which
    would collapse all clients into one bucket; PARKWISE_TRUSTED_PROXY_HEADER then
    enables X-Forwarded-For / Forwarded parsing. Leave it unset unless the immediate
    upstream is one you control, since a client can otherwise forge its own address.
    """
    if authorization or x_api_key:
        return "key:" + hash_key((authorization or x_api_key))[:16]
    return "ip:" + client_ip(request)


def client_ip(request: Request) -> str:
    header = env_settings.trusted_proxy_header.strip().lower()
    if header:
        value = request.headers.get(header)
        if value:
            # X-Forwarded-For is a chain; the left-most entry is the client.
            first = value.split(",")[0].strip()
            if first:
                return first
        forwarded = request.headers.get("forwarded")
        if forwarded:
            for part in forwarded.split(";"):
                key, _, val = part.strip().partition("=")
                if key.lower() == "for":
                    return val.strip('"').split(",")[0].strip() or "unknown"
    return request.client.host if request.client else "anonymous"


def rate_limit(
    request: Request,
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> None:
    """Dependency for mutating endpoints; buckets keyed by API key when sent, else IP."""
    limit = env_settings.rate_limit_per_minute
    if limit <= 0:
        return
    rate_limiter.check(client_identity(request, authorization, x_api_key), limit)


# ---------------------------------------------------------------------------
# Signed media URLs (preview / original / annotated / snapshot).
#
# Browsers load <img>, <video> and file downloads without custom headers, so
# the media endpoints cannot rely on X-API-Key the way JSON APIs do. Every media
# URL handed out by the API therefore carries a short-lived HMAC signature bound
# to (purpose, object id, expiry): a preview signature cannot fetch the original
# video, and nothing signed here authenticates any non-media endpoint.
#
# Unlike the single-use WebSocket tickets, signatures are multi-use until `exp`
# because one page may re-read the same image several times. The secret is
# PARKWISE_MEDIA_SIGNING_SECRET when set (stable across restarts and replicas);
# otherwise a random per-process secret is generated, which simply invalidates
# outstanding URLs on restart — acceptable inside the single-process runtime.
# ---------------------------------------------------------------------------

_media_secret_lock = threading.Lock()
_process_media_secret: str | None = None


def media_secret() -> str:
    configured = env_settings.media_signing_secret.strip()
    if configured:
        return configured
    global _process_media_secret
    with _media_secret_lock:
        if _process_media_secret is None:
            _process_media_secret = secrets.token_urlsafe(32)
        return _process_media_secret


def _media_signature(purpose: str, object_id: str, exp: int) -> str:
    message = f"{purpose}|{object_id}|{exp}".encode("utf-8")
    return hmac.new(media_secret().encode("utf-8"), message, hashlib.sha256).hexdigest()


def sign_media(path: str, purpose: str, object_id: str, *, expires_at: int | None = None) -> str:
    """Append ``sig``/``exp`` query params to a media path (used in API responses)."""
    exp = expires_at if expires_at is not None else int(time.time()) + env_settings.media_url_ttl_seconds
    sep = "&" if "?" in path else "?"
    return f"{path}{sep}sig={_media_signature(purpose, object_id, exp)}&exp={exp}"


def verify_media_signature(purpose: str, object_id: str, sig: str | None, exp: int | None) -> bool:
    if not sig or exp is None:
        return False
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(_media_signature(purpose, object_id, exp), sig)


def media_scope(request: Request) -> tuple[str, str]:
    """Derive (purpose, object id) from the routed media path being requested."""
    params = request.path_params
    if "video_id" in params:
        kind, object_id = "video", str(params["video_id"])
    elif "stream_id" in params:
        kind, object_id = "stream", str(params["stream_id"])
    else:  # pragma: no cover - only reachable if a route forgets its path param
        kind, object_id = "", ""
    action = request.url.path.rstrip("/").rsplit("/", 1)[-1]
    return f"{kind}.{action}", object_id


def media_access(
    request: Request,
    db: Session = Depends(get_db),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
    sig: str | None = Query(default=None),
    exp: int | None = Query(default=None),
) -> User | None:
    """Authenticate a media request: a valid signed URL, else the normal API-key rules.

    Attached (router-level) to the media-only routers so JSON endpoints never
    accept signatures, and so a signature for one object/purpose never grants
    access to another.
    """
    purpose, object_id = media_scope(request)
    if verify_media_signature(purpose, object_id, sig, exp):
        return None
    return current_user(db=db, authorization=authorization, x_api_key=x_api_key)
