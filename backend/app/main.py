import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings, validate_startup_config
from .database import SessionLocal, init_db
from .api.routes import router as videos_router
from .api.routes import health_router as videos_health_router
from .api.routes import media_router as videos_media_router
from .api.routes import ws_router as videos_ws_router
from .api.insights import router as insights_router
from .api.live import router as live_router
from .api.live import media_router as live_media_router
from .api.live import ws_router as live_ws_router
from .api.admin import router as admin_router
from .security import AUTH_LIMIT_PER_MINUTE, auth_limiter, client_ip
from .services import job_claim
from .services.live_stream import manager as stream_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def _enforce_startup_safety() -> None:
    """Fail closed on unsafe configuration (production rules + exposed-no-auth bind)."""
    problems = validate_startup_config(settings)
    if problems:
        raise RuntimeError("Refusing to start with unsafe configuration: " + "; ".join(problems))


@asynccontextmanager
async def lifespan(app: FastAPI):
    _enforce_startup_safety()
    settings.ensure_dirs()  # create uploads/previews/processed/streams up front
    init_db()
    # Rows left mid-flight by a crash/restart would stay "processing" forever: they
    # block reprocess, delete and calibration, and hold a Starter plan's single
    # concurrent-job slot permanently.
    db = SessionLocal()
    try:
        # startup=True: nothing survives a restart in-process, so every queued
        # row (and any lease-less "processing" row) is already unreachable.
        reaped = job_claim.reap_stale(db, startup=True)
        if reaped["expired_leases"] or reaped["abandoned_queue"]:
            logger.warning(
                "Recovered %s interrupted job(s) (%s expired leases, %s never started)",
                reaped["expired_leases"] + reaped["abandoned_queue"],
                reaped["expired_leases"],
                reaped["abandoned_queue"],
            )
    finally:
        db.close()
    stream_manager.reset_on_startup()
    yield
    stream_manager.shutdown()


_docs_enabled = settings.env.strip().lower() != "production"
app = FastAPI(
    title="ParkWise AI API",
    description=(
        "Video-based parking occupancy analysis, live camera streams and analytics. "
        "Empty datasets remain empty until real video is processed."
    ),
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)


# Registered before CORS so CORS ends up outermost and every response (including a
# 429 produced here) still carries the browser's required headers.
@app.middleware("http")
async def failed_auth_budget(request, call_next):
    """Cap credential probing (API4/API6).

    Every rejected key costs a database lookup, so anonymous brute force is limited
    much harder than ordinary traffic: once a client has collected
    AUTH_LIMIT_PER_MINUTE 401s in a window, further attempts are refused outright.
    """
    response = await call_next(request)
    if settings.auth_required and response.status_code == 401:
        allowed, retry = auth_limiter.try_consume(client_ip(request), AUTH_LIMIT_PER_MINUTE)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Too many failed authentication attempts; retry in {retry}s"},
                headers={"Retry-After": str(retry)},
            )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(videos_router)
app.include_router(videos_health_router)
app.include_router(videos_media_router)
app.include_router(videos_ws_router)
app.include_router(insights_router)
app.include_router(live_router)
app.include_router(live_media_router)
app.include_router(live_ws_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {
        "name": "ParkWise AI",
        "api_docs": "/docs" if _docs_enabled else None,
        "health": "/api/health",
    }


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logging.getLogger(__name__).exception("Unhandled server error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred. Check API logs for details."})
