import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from .config import settings
from .database import init_db
from .api.routes import router as videos_router
from .api.insights import router as insights_router
from .api.live import router as live_router
from .api.live import ws_router as live_ws_router
from .api.admin import router as admin_router
from .services.live_stream import manager as stream_manager

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.data_path
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
