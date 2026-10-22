# ParkWise AI

**Video-driven parking intelligence, built around Python.** ParkWise AI analyzes actual uploaded or approved public parking footage, runs vehicle detection and multi-object tracking, stores measured results, and serves a web dashboard. It does not manufacture sample KPIs: a fresh installation has empty analytics until real footage has been processed.

> **Current release scope:** runnable foundation for offline/public-video analysis, user-defined parking-space polygons, annotated output, detection timelines, WebSocket job status, SQLite by default, and a Next.js dashboard. It is not yet a certified safety system or a plug-and-play production live-camera deployment. Public stock videos are demonstrations, not live views of an operating facility.

## Features

- Next.js + TypeScript + responsive dark/light operations dashboard with a top-bar theme toggle (the choice is stored per browser).
- FastAPI/Python backend with SQLAlchemy persistence and OpenAPI docs.
- Upload a video or fetch one of three verified public Pexels parking clips (network access required at runtime).
- Python/OpenCV video inspection, YOLO26 vehicle detection, ByteTrack IDs, annotated H.264 MP4 output and preview frames.
- Adaptive multi-scale inference: frames that report almost no vehicles at the configured image size are re-run at 2560 px and native resolution before a count is stored (`PARKWISE_MULTISCALE`).
- Define parking bay regions by drawing normalized polygons over a real source video's preview; occupancy is assessed per configured region.
- Real analytics from stored processing samples, including observed vehicle-count series, peak observed count, average confidence and slot occupancy.
- Job states and progress updates; REST + WebSocket status endpoint.
- Docker Compose, backend tests, CI workflow, API and AI notes, licensing/security guidance.
- No included fake parking video, stock image, seeded customer, or hard-coded KPI values.

## Quick start (Docker)

Requirements: Docker Desktop or Docker Engine with Compose, and an internet connection on first build (to pull packages, footage, and model weights).

```bash
cp .env.example .env
docker compose up --build
```

Open:

- Web dashboard: <http://localhost:3000>
- API health: <http://localhost:8000/api/health>
- Interactive API docs: <http://localhost:8000/docs>

On Windows PowerShell, use `Copy-Item .env.example .env` instead of `cp`.

### First run

1. In the dashboard, go to **Video Lab**.
2. Upload your own permitted parking footage, or choose **Fetch public footage** and select one of the linked Pexels clips.
3. Wait for the source to be saved and inspected. The displayed duration/resolution come from the video file.
4. (Recommended for slot occupancy) Open **Space Calibration**, select the video, click points around each parking bay in the preview, and save each polygon. Use a fixed, static camera angle; calibrate each camera/angle separately.
5. Return to Video Lab and click **Analyze**. The first inference run may download `yolo26s.pt`, depending on the model cache.
6. Review annotated output and analytics. If you did not calibrate spaces, the system reports frame-level vehicle detections; it will not pretend these are free/occupied slot counts.

On CPU, expect roughly 1–2 minutes for a short 1080p clip and about 30 minutes for the 38 s 4K public clip with multi-scale enabled. Progress is shown in the dashboard while the job runs.

## Run without Docker

Python 3.12 recommended; Node.js 22+ recommended. If the system `python3` is a newer release without binary wheels for the CV stack, pin the interpreter when creating the venv, e.g. `uv venv --python 3.12 .venv` (then `source .venv/bin/activate`).

```bash
python3 -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r backend/requirements.txt
# Always start the server through the venv interpreter:
.venv/bin/python3 -m uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

If you type a bare `uvicorn` command and the shell resolves it to a global/user install (common after
activating a venv in a shell where that command ran before), the server starts under the wrong Python
and fails on import with `ModuleNotFoundError: No module named 'cv2'`. Run `hash -r` after activating,
or use the `.venv/bin/python3 -m uvicorn ...` form above / `scripts/run_local.sh`, which always launches
the virtualenv interpreter.

In a second terminal:

```bash
cd web
npm install
# Create web/.env.local with NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

`scripts/run_local.sh` performs the same setup (venv, packages, `web/.env.local`) and starts both services in one terminal with `python3`.

The detector weights are downloaded by Ultralytics when first used. For a GPU, install a PyTorch build matched to your CUDA driver before installing the remaining packages; see the model guide.

## Configuration

Copy `.env.example` to `.env`. Most useful settings:

- `PARKWISE_MODEL`: default `yolo26s.pt`; may be changed to another supported vehicle detector such as `yolo26n.pt`, `yolo11s.pt` or `rtdetr-l.pt` after validating compatibility and performance.
- `PARKWISE_CONFIDENCE`: detector confidence threshold.
- `PARKWISE_FRAME_STRIDE`: process every Nth frame to trade speed for temporal detail.
- `PARKWISE_MULTISCALE`: when a frame yields almost no vehicles at `PARKWISE_IMAGE_SIZE`, re-run that frame at sharper resolutions (up to native) before reporting the count. Disable to cap CPU cost on long 4K clips.
- `PARKWISE_MAX_UPLOAD_MB`: upload and public-source size limit.
- `PARKWISE_DATABASE_URL`: SQLite by default; for deployment use a managed PostgreSQL instance and install a PostgreSQL driver.
- `PARKWISE_ALLOWED_ORIGINS`: comma-separated frontend origins.

## Real footage used for the public-source picker

The source catalogue uses direct MP4 locations resolved from Pexels' public download pages. They are downloaded only when an operator clicks **Fetch**. Please re-check applicable terms before redistribution or commercial use; footage is credited to its creator in the UI and source registry.

1. [Tom Fisk — Aerial Footage Of Cars On A Parking Lot](https://www.pexels.com/video/aerial-footage-of-cars-on-a-parking-lot-3848792/) — 38 seconds, 3840×2160, 29.97 FPS. Direct file URL in `backend/app/services/public_sources.py`.
2. [Yasin Koçtepe — An aerial view of a parking lot with cars](https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-27832493/) — 18 seconds, 3840×2160, 50 FPS.
3. [David Pickup — An aerial view of a parking lot with cars](https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-28125313/) — 31 seconds, 3840×2160, 29.97 FPS.

The project archive does not bundle these large third-party videos: the build environment could not establish a direct internet connection to download and verify binary assets. The app fetches the real sources from their listed URLs when run in an internet-connected environment, and also accepts your own files.

## Architecture (high level)

```text
Public Pexels MP4 / permitted upload / (planned RTSP camera adapter)
                      │
                      ▼
           FastAPI source & upload API
                      │
                      ▼
      OpenCV inspection + YOLO vehicle detector
                 + ByteTrack IDs
                      │
          ┌───────────┴────────────┐
          ▼                        ▼
  Per-space polygon match    Frame-level samples
          │                        │
          └───────────┬────────────┘
                      ▼
       SQLAlchemy persistence (SQLite default)
                      │
            REST + WebSocket API
                      │
                      ▼
         Next.js / TypeScript dashboard
```

## Repository structure

```text
parkwise-ai/
├── backend/                 # Python API, SQLAlchemy models and CV pipeline
│   ├── app/api/             # route modules
│   ├── app/services/        # video inference and public-source fetcher
│   └── tests/
├── web/                     # Next.js App Router / TypeScript / CSS
├── data/                    # runtime data only; excluded from git/archive except .gitkeep
├── docs/                    # architecture, model guide, API and security notes
├── scripts/                 # run_local.sh launcher, source and validation utilities
├── docker-compose.yml
└── .github/workflows/       # CI
```

## API outline

- `GET /api/health`
- `GET /api/config/public`
- `GET /api/dashboard/summary`
- `GET /api/videos`
- `POST /api/videos/upload` — multipart field `file`
- `POST /api/public-sources/{source_id}/fetch`
- `GET /api/videos/{video_id}`
- `DELETE /api/videos/{video_id}` — removes the job, its samples, calibration and media files
- `POST /api/videos/{video_id}/process`
- `GET /api/videos/{video_id}/preview`
- `GET /api/videos/{video_id}/original`
- `GET /api/videos/{video_id}/annotated`
- `GET /api/videos/{video_id}/spaces`
- `POST /api/videos/{video_id}/spaces`
- `DELETE /api/videos/{video_id}/spaces/{space_id}`
- `GET /api/videos/{video_id}/analytics`
- `GET /api/videos/{video_id}/occupancy` — per-bay free/occupied history from the last run
- `WS /api/ws/videos/{video_id}`

Full interactive schemas are available at `/docs`.

## Validation

```bash
# with the venv activated (see "Run without Docker")
python3 -m pytest -q backend/tests
python3 scripts/check_project.py
```

Tests focus on API health, empty-state honesty, source allowlisting, polygon validation, and analytics behavior. Model inference tests require an actual model cache and video and are intentionally separated from the fast test suite. Frontend checks: `cd web && npm run lint && npx tsc --noEmit && npm run build`. What has been verified on a live machine is recorded in `docs/BUILD_STATUS.md`.

## Important limitations / next production steps

- A stock clip is recorded footage, not a live camera, and does not certify a real parking site's availability. Use a camera you control for operational decisions.
- Polygon matching is a baseline: calibrate fixed camera views, validate in day/night/weather and occlusion conditions, and measure precision/recall against labelled ground truth before using it operationally.
- Extreme aerial zoom-out can shrink a vehicle to a few pixels; even native-resolution inference may then report 0 for a frame. The pipeline records the measured 0 instead of estimating a count.
- Occupancy is **unknown** when there is no calibrated space geometry; no free-space count is estimated from a raw vehicle total.
- This release is single-tenant and intended for local pilots. Add managed Postgres, object storage, a durable queue, auth/RBAC, tenant isolation, retention automation, and observability before exposing it publicly.
- Ultralytics package/model licensing is deployment-dependent; review `docs/AI_MODELS.md` and obtain the appropriate license if needed.

## License

This repository's source code is MIT-licensed under `LICENSE`. Third-party model weights, videos, and dependencies remain subject to their own terms. A repository-level MIT license does not override those terms.
# PARK_WISE_AI
