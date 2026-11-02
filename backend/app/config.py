from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARKWISE_", env_file=".env", extra="ignore")

    env: str = "development"
    # Loopback by default: exposing an unauthenticated API to the network must be a
    # deliberate choice (validate_startup_config refuses non-loopback binds with auth off).
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "sqlite:///./data/parkwise.db"
    data_dir: str = "./data"
    # Media bytes: "local" keeps the historical data_dir layout, "blob" uses
    # Vercel Blob (required on serverless, where the filesystem is ephemeral).
    storage_backend: str = "local"
    # Scratch space for OpenCV/ffmpeg when the real filesystem is read-only
    # (Vercel functions expose a sized /tmp). Empty = system temp dir.
    tmp_dir: str = ""
    # Vercel Blob store origin that serves objects, e.g.
    # "https://abc123.us1.blob.vercel-storage.com". Public stores only.
    blob_public_url: str = ""
    # "public" = objects are served by the store's CDN (redirects from the API);
    # "private" = the API streams the bytes itself, keeping per-role access checks.
    blob_access: str = "public"
    max_upload_mb: int = 250
    max_video_seconds: int = 1800
    model: str = "yolo26s.pt"
    confidence: float = 0.25
    image_size: int = 1280
    frame_stride: int = 3
    device: str = "auto"
    multiscale: bool = True
    auto_download_public_sources: bool = True
    # Security / limits (0 disables a check; see docs/SECURITY.md)
    auth_required: bool = False
    rate_limit_per_minute: int = 240
    # Comma-separated CIDR allowlist for private camera networks, e.g.
    # "192.168.1.0/24,10.0.0.0/8". Empty = all private ranges allowed (LAN CCTV default).
    trusted_camera_cidrs: str = ""
    # Name of the header the *immediately trusted* reverse proxy uses to carry the
    # client address, e.g. "x-forwarded-for". Empty (default) reads the socket peer,
    # because any client can forge this header when the app is directly reachable.
    trusted_proxy_header: str = ""
    # Live view streaming
    stream_width: int = 960
    stream_quality: int = 72
    stream_max_seconds: int = 0  # 0 = run until stopped; guard against runaway sources
    stream_stale_seconds: int = 10  # no fresh frame for this long => status "stale"
    stream_max_reconnect_attempts: int = 5  # bounded reconnects with exponential backoff

    @property
    def origins(self) -> list[str]:
        """Explicit CORS allowlist, with loopback aliases treated as equivalent.

        Browsers cannot fetch http://localhost:8000 from an http://0.0.0.0:3000
        page (or vice versa) unless both names are allowed, and Next's dev banner
        advertises the 0.0.0.0 URL. Mirroring each loopback host across the usual
        aliases lets local development work without widening the list to a
        wildcard — anything non-loopback must still be listed explicitly.
        """
        origins: list[str] = []
        for origin in self.allowed_origins.split(","):
            origin = origin.strip().rstrip("/")
            if origin and origin not in origins:
                origins.append(origin)
        loopback_aliases = {"http://localhost", "http://127.0.0.1", "http://[::1]", "http://0.0.0.0"}
        for origin in list(origins):
            scheme, _, rest = origin.partition("://")
            host, _, port = rest.partition(":")
            if f"{scheme}://{host}" not in loopback_aliases:
                continue
            for alias in loopback_aliases:
                candidate = alias if not port else f"{alias}:{port}"
                if candidate not in origins:
                    origins.append(candidate)
        return origins

    def ensure_dirs(self) -> Path:
        """Create (if needed) and return the runtime data root."""
        path = Path(self.data_dir).expanduser().resolve()
        folders = ("streams",) if self.storage_backend.strip().lower() == "blob" else ("uploads", "processed", "previews", "streams")
        for folder in folders:
            try:
                (path / folder).mkdir(parents=True, exist_ok=True)
            except OSError:
                # Blob mode keeps media off this filesystem and a serverless root is
                # read-only; only live-view JPEG snapshots genuinely need a directory.
                if folder != "streams":
                    raise
        return path

    @property
    def data_path(self) -> Path:
        return self.ensure_dirs()


def validate_startup_config(settings: "Settings") -> list[str]:
    """Return a list of fatal configuration problems (empty when safe to run).

    Fails closed in two independent ways:

    * Production (PARKWISE_ENV=production) requires secure authentication and an
      explicit CORS allowlist.
    * In *any* environment, running with authentication disabled while binding a
      non-loopback interface would publish an unauthenticated admin API to the
      network — that combination is refused outright, not warned about.
    """
    import os

    problems: list[str] = []
    if settings.env.strip().lower() == "production":
        if not settings.auth_required:
            problems.append("PARKWISE_AUTH_REQUIRED must be true when PARKWISE_ENV=production")
        origins = settings.origins
        if not origins or any(origin == "*" for origin in origins):
            problems.append("PARKWISE_ALLOWED_ORIGINS must be an explicit list (no wildcard) in production")
    if not settings.auth_required and not is_loopback_bind(settings.api_host):
        problems.append(
            f"PARKWISE_AUTH_REQUIRED=false cannot be combined with PARKWISE_API_HOST={settings.api_host}: "
            "binding a non-loopback interface without authentication exposes the admin API to the network. "
            "Either enable auth (PARKWISE_AUTH_REQUIRED=true) or bind loopback (PARKWISE_API_HOST=127.0.0.1)"
        )
    if settings.storage_backend.strip().lower() == "blob":
        if not (
            os.environ.get("BLOB_READ_WRITE_TOKEN")
            or os.environ.get("VERCEL_BLOB_READ_WRITE_TOKEN")
            or os.environ.get("BLOB_STORE_ID")
        ):
            problems.append(
                "PARKWISE_STORAGE=blob needs BLOB_READ_WRITE_TOKEN (or BLOB_STORE_ID with Vercel OIDC)"
            )
        if settings.blob_access.strip().lower() not in {"public", "private"}:
            problems.append("PARKWISE_BLOB_ACCESS must be 'public' or 'private'")
    return problems


def is_loopback_bind(host: str) -> bool:
    return host.strip() in {"127.0.0.1", "localhost", "::1", "[::1]"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
