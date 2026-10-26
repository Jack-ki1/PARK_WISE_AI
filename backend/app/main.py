import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import is_loopback_bind, settings, validate_startup_config
from .database import init_db
from .api.routes import router as videos_router
from .api.routes import ws_router as videos_ws_router
from .api.insights import router as insights_router
from .api.live import router as live_router
from .api.live import ws_router as live_ws_router
from .api.admin import router as admin_router
from .services.live_stream import manager as stream_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger(__name__)


def _enforce_startup_safety() -> None:
    """Fail closed on unsafe production config; warn on exposed local-only mode."""
    problems = validate_startup_config(settings)
    if problems:
        raise RuntimeError("Refusing to start with unsafe configuration: " + "; ".join(problems))
    if not settings.auth_required and not is_loopback_bind(settings.api_host):
        logger.warning(
            "PARKWISE_AUTH_REQUIRED=false with api_host=%s: unauthenticated access is "
            "reachable beyond loopback. Bind to 127.0.0.1 for local-only development "
            "or enable authentication for any network-exposed deployment.",
            settings.api_host,
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    _enforce_startup_safety()
    settings.ensure_dirs()  # create uploads/previews/processed/streams up front
    init_db()
    stream_manager.reset_on_startup()
    yield
    stream_manager.shutdown()


app = FastAPI(
    title="ParkWise AI API",
    description=(
        "Video-based parking occupancy analysis, live camera streams and analytics. "
        "Empty datasets remain empty until real video is processed."
    ),
    version="2.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)
app.include_router(videos_router)
app.include_router(videos_ws_router)
app.include_router(insights_router)
app.include_router(live_router)
app.include_router(live_ws_router)
app.include_router(admin_router)


@app.get("/")
def root():
    return {"name": "ParkWise AI", "api_docs": "/docs", "health": "/api/health"}


@app.exception_handler(500)
async def internal_error_handler(request, exc):
    logging.getLogger(__name__).exception("Unhandled server error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": "An unexpected server error occurred. Check API logs for details."})
