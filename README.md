# ParkWise AI

**Video-driven parking intelligence, built around Python.** ParkWise AI analyzes actual uploaded or approved public parking footage, runs vehicle detection and multi-object tracking, stores measured results, and serves a web dashboard. It does not manufacture sample KPIs: a fresh installation has empty analytics until real footage has been processed.

> **Current release scope:** runnable foundation for offline/public-video analysis, real-time RTSP/HTTP or replay streams with per-bay occupancy, API-key auth with roles, user-defined parking-space polygons, annotated output, detection timelines, WebSocket job status/frames, SQLite by default, and a Next.js dashboard. It is not yet a certified safety system or a plug-and-play production live-camera deployment (no durable job queue, no tenant isolation). Public stock videos are demonstrations, not live views of an operating facility.

---

## Table of contents

1. [What this project is (and is not)](#what-this-project-is-and-is-not) 2. [Features](#features) 3. [Requirements](#requirements) 4. [Quick start (Docker)](#quick-start-docker) 5. [Run without Docker](#run-without-docker) 6. [First run walkthrough](#first-run-walkthrough) 7. [Using the dashboard](#using-the-dashboard) 8. [Configuration](#configuration) 9. [Authentication and roles](#authentication-and-roles) 10. [Live cameras and replay streams](#live-cameras-and-replay-streams) 11. [How the pipeline works](#how-the-pipeline-works) 12. [Real footage used for the public-source picker](#real-footage-used-for-the-public-source-picker) 13. [Architecture](#architecture) 14. [Repository structure](#repository-structure) 15. [API outline](#api-outline) 16. [Data model](#data-model) 17. [Validation and tests](#validation-and-tests) 18. [Troubleshooting](#troubleshooting) 19. [Deployment notes](#deployment-notes) 20. [Performance expectations](#performance-expectations) 21. [Privacy and safety](#privacy-and-safety) 22. [Limitations / next production steps](#limitations--next-production-steps) 23. [Contributing](#contributing) 24. [Documentation index](#documentation-index) 25. [License](#license)

---

## What this project is (and is not)

ParkWise AI turns parking video into measurements. You give it footage or a camera, it detects vehicles, tracks them, checks each detected vehicle against the parking bays you drew on the frame, and persists the result. The dashboard then shows what was actually measured.

| It is | It is not |
| --- | --- |
| A working Python/OpenCV/YOLO inference pipeline | A certified occupancy or safety system |
| A real dashboard backed by persisted database rows | A mockup with hard-coded KPI numbers |
| A local pilot deployment with API-key RBAC | A multi-tenant SaaS platform |
| Honest about uncertainty (occupancy is `unknown` without geometry) | A system that guesses free-space counts from raw vehicle totals |

Every metric shown traces back to a stored `DetectionSample` or `OccupancySample` row produced by a real processing run.

## Features

- Next.js + TypeScript + responsive dark/light operations dashboard with a top-bar theme toggle (the choice is stored per browser).
- FastAPI/Python backend with SQLAlchemy persistence and OpenAPI docs.
- Upload a video or fetch one of three verified public Pexels parking clips (network access required at runtime).
- Python/OpenCV video inspection, YOLO26 vehicle detection, ByteTrack IDs, annotated H.264 MP4 output and preview frames.
- Adaptive multi-scale inference: frames that report almost no vehicles at the configured image size are re-run at 2560 px and native resolution before a count is stored (`PARKWISE_MULTISCALE`).
- Define parking bay regions by drawing normalized polygons over a real source video's preview; occupancy is assessed per configured region.
- Real analytics from stored processing samples, including observed vehicle-count series, peak observed count, average confidence and slot occupancy.
- Live view: point a stream at an RTSP/HTTP camera URL or replay an uploaded video, draw bay polygons on a captured frame, and receive annotated frames over a ticketed WebSocket with live/replay labelling and stale-frame warnings. Overcrowding on a calibrated stream fires the configured webhook.
- API-key authentication with `admin`/`operator`/`viewer` roles, rate limiting on mutations, ticket-only WebSocket auth (no durable keys in URLs), and a production fail-closed startup check.
- Job states and progress updates; REST + WebSocket status endpoint.
- Activity feed recording operator and system events with a bounded retention.
- Docker Compose, backend tests, CI workflow, API and AI notes, licensing/security guidance.
- No included fake parking video, stock image, seeded customer, or hard-coded KPI values.

## Requirements

| Component | Version | Notes |
| --- | --- | --- |
| Python | 3.12 recommended | Must have binary wheels for `opencv`/`torch`. Newer system Pythons may not. |
| Node.js | 20+ (22+ recommended) | `web/package.json` declares `engines.node >= 20`. |
| Docker | Desktop or Engine + Compose | Only needed for the Docker path. |
| Disk | ~2–3 GB | PyTorch + Ultralytics dominate; model weights add tens-to-hundreds of MB. |
| Network | First run only, ideally | For pip/npm installs, model weights, and public-source downloads. |

**GPU (optional).** CPU inference works out of the box. For CUDA, install a PyTorch build matching your driver *before* installing the rest, then set `PARKWISE_DEVICE=cuda`. See [docs/AI_MODELS.md](docs/AI_MODELS.md).

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

What Compose starts:

- `api` — the FastAPI service, built from `backend/Dockerfile`, published on `8000`, data volume `parkwise_data` mounted at `/srv/data`, `shm_size: 1gb` for inference memory, healthcheck polling `/api/health`.
- `web` — the Next.js dashboard, built from `web/Dockerfile`, published on `3000`, and gated with `depends_on: api → service_healthy` so the UI never boots against a dead API.

To stop, press `Ctrl+C`; to remove the stack use `docker compose down`. Add `-v` only if you also want to delete the persisted videos and database.

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

Why the explicit `.venv/bin/python3 -m uvicorn` form matters: if you type a bare `uvicorn` and the shell resolves it to a global or user install (`~/.local/bin/uvicorn`), the server starts under the *wrong* Python. On a system Python without `cv2`, that fails at import with:

```text
ModuleNotFoundError: OpenCV (cv2) is missing from this interpreter.
```

That message comes from `backend/app/services/video_pipeline.py`, which checks `cv2` at import time. Run `hash -r` after activating, or use the form above / `scripts/run_local.sh`, which always launches the virtualenv interpreter.

In a second terminal:

```bash
cd web
npm install
# Create web/.env.local with NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

### The one-command launcher

`scripts/run_local.sh` performs the same setup (creates `.venv` if missing, installs backend and web dependencies, writes `web/.env.local`) and starts both services in one terminal:

```bash
./scripts/run_local.sh
```

It launches the API with `.venv/bin/python3 -m uvicorn`, then **waits for `/api/health` to answer before printing the URLs**, so you never open the dashboard against a booting API and see a false "API offline" banner. It also rewrites `web/.env.local` whenever the expected URL differs, mapping a `0.0.0.0` bind to `localhost` for the browser.

### About `NEXT_PUBLIC_API_BASE_URL`

This value is **inlined into the browser bundle at compile time**. Changing it requires restarting `next dev` (or rebuilding) — it is not read live from the file. Because a browser tab loaded from `http://0.0.0.0:3000` sends `Origin: http://0.0.0.0:3000`, the API's CORS allowlist mirrors loopback hostnames (`localhost`, `127.0.0.1`, `[::1]`, `0.0.0.0`) for any loopback origin that is already allowed. Non-loopback origins must be listed explicitly.

## First run walkthrough

1. In the dashboard sidebar open **Live View**.
2. Under **Import a video**, upload your own permitted parking footage, or under **Fetch real parking clips** select one of the linked Pexels sources.
3. Wait for the source to be saved and inspected. The displayed duration/resolution come from the video file.
4. (Recommended for slot occupancy) In **Imported video jobs** select the video, open the bay polygon editor and click points around each parking bay in the preview, then save the polygon. Use a fixed, static camera angle; calibrate each camera/angle separately.
5. Click **Analyze with these bays**. The first inference run may download `yolo26s.pt`, depending on the model cache.
6. Review annotated output and analytics. If you did not calibrate spaces, the system reports frame-level vehicle detections; it will not pretend these are free/occupied slot counts.
7. For a camera instead of a file, add a stream under **Streams** (RTSP/HTTP URL or an uploaded video as replay), **Start** it, then **Calibrate bays** on a captured frame. Frames arrive in the viewer over a ticketed WebSocket.

## Using the dashboard

The dashboard is a single-page operations console (`web/app/dashboard/page.tsx`) with a left sidebar, a top bar showing connection status, and these pages:

- **Dashboard** — aggregate KPIs from `/api/dashboard/summary` and `/api/dashboard/analytics`: video counts, observed vehicle series, peak observed count, average confidence and per-bay occupancy. Refreshes every 5 seconds, paused while the tab is hidden and resumed on focus.
- **Live View** — video import, public-source fetching, the bay polygon editor, job progress over WebSocket, annotated output, and the streams table with start/stop/snapshot/calibration.
- **Reports & Settings** — model and inference settings, integration webhook, map preferences, user management, and local billing plan.
- **Activity** — `/api/activity` operator/system event feed.

The top bar shows a connection chip reflecting `/api/health`: `Connecting`, `API connected`, or `API offline`. If the API is unreachable, the page keeps its last known data on screen and shows why the request failed rather than an anonymous "Failed to fetch".

## Configuration

Copy `.env.example` to `.env`. The backend reads these through `pydantic-settings` with the `PARKWISE_` prefix (`backend/app/config.py`).

### Core

| Variable | Default | Meaning |
| --- | --- | --- |
| `PARKWISE_ENV` | `development` | `production` enables fail-closed startup checks. |
| `PARKWISE_API_HOST` | `0.0.0.0` | Bind host used by `scripts/run_local.sh`. |
| `PARKWISE_API_PORT` | `8000` | Bind port; also written into `web/.env.local`. |
| `PARKWISE_ALLOWED_ORIGINS` | `http://localhost:3000,http://127.0.0.1:3000` | Comma-separated browser origins for CORS. |
| `PARKWISE_DATABASE_URL` | `sqlite:///./data/parkwise.db` | SQLAlchemy URL. Use Postgres for deployment. |
| `PARKWISE_DATA_DIR` | `./data` | Root for `uploads/`, `processed/`, `previews/`, `streams/`. |
| `PARKWISE_MAX_UPLOAD_MB` | `250` | Upload and public-source size limit. |
| `PARKWISE_MAX_VIDEO_SECONDS` | `1800` | Rejected duration ceiling. |

### Inference

| Variable | Default | Meaning |
| --- | --- | --- |
| `PARKWISE_MODEL` | `yolo26s.pt` | Detector weights. Others: `yolo26n.pt`, `yolo11s.pt`, `rtdetr-l.pt`. |
| `PARKWISE_CONFIDENCE` | `0.25` | Detector confidence threshold. |
| `PARKWISE_IMAGE_SIZE` | `1280` | Inference resolution; higher costs more CPU/GPU. |
| `PARKWISE_MULTISCALE` | `true` | Re-run near-empty frames at sharper resolutions (up to native). |
| `PARKWISE_FRAME_STRIDE` | `3` | Process every Nth frame; trades speed for temporal detail. |
| `PARKWISE_DEVICE` | `auto` | `auto`, `cpu`, or `cuda`. |

### Security

| Variable | Default | Meaning |
| --- | --- | --- |
| `PARKWISE_AUTH_REQUIRED` | `false` | `true` makes every request require a key (mandatory in production). |
| `PARKWISE_RATE_LIMIT_PER_MINUTE` | `240` | Per-client budget for mutating requests; `0` disables. |
| `PARKWISE_TRUSTED_CAMERA_CIDRS` | *(empty)* | CIDR allowlist for on-prem cameras; empty allows all private ranges. |

### Live view

| Variable | Default | Meaning |
| --- | --- | --- |
| `PARKWISE_STREAM_WIDTH` | `960` | Width of encoded frames sent over the WebSocket. |
| `PARKWISE_STREAM_QUALITY` | `72` | JPEG quality for streamed frames. |
| `PARKWISE_STREAM_MAX_SECONDS` | `0` | `0` = run until the client disconnects. |
| `PARKWISE_STREAM_STALE_SECONDS` | `10` | No fresh frame for this long ⇒ status `stale`. |
| `PARKWISE_STREAM_MAX_RECONNECT_ATTEMPTS` | `5` | Bounded reconnects with exponential backoff. |

### Frontend

| Variable | Default | Meaning |
| --- | --- | --- |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Public API origin baked into the browser bundle. No trailing slash. |

### Settings stored in the database

Some settings are editable at runtime from **Settings** and take effect on the next analysis run or live session, without a restart (`backend/app/services/settings_store.py`): `model`, `confidence`, `image_size`, `frame_stride`, `device`, `multiscale`, `plan`, `webhook_url`, `webhook_secret`, `map_center`, `map_style`, `public_sources_enabled`. Each is validated on write — `confidence` must be within `0.05–0.95`, `image_size` within `320–2560`, `frame_stride` within `1–30`.

## Authentication and roles

Authentication is off by default for local development and **must** be on for anything reachable from a network.

1. Create the first administrator (works with the API stopped or running):

   ```bash
   .venv/bin/python3 scripts/bootstrap_admin.py --username admin --display-name "Admin"
   ```

   The script refuses to run if an active admin already exists, generates a cryptographically secure key, and prints it **once**. Save it immediately — it is never stored in plaintext (only a hash is persisted).

2. Send the key as `X-API-Key: pk_…` or `Authorization: Bearer pk_…`.

3. Additional users are created under **Settings → Users** and receive their own `pk_…` key shown once. Keys can be rotated (`POST /api/users/{id}/rotate-key`).

| Role | Can do |
| --- | --- |
| `viewer` | Read videos, analytics, streams, activity. All mutations return `403`. |
| `operator` | Everything a viewer can, plus upload/process/delete videos, manage bays, and control streams. |
| `admin` | Everything, plus user management, API-key rotation, billing and integration settings. |

Safeguards: the last active admin cannot be deleted or deactivated; the key lives in `sessionStorage` only and disappears with the tab; WebSockets never carry durable keys (see below).

### WebSocket authentication

Browsers cannot set headers on a WebSocket handshake. Both WebSockets therefore require a short-lived, single-use ticket:

```bash
# 1. Mint a ticket over authenticated REST
curl -H "X-API-Key: pk_..." -X POST http://localhost:8000/api/videos/{video_id}/ws-ticket

# 2. Connect with the ticket, not the key
ws://localhost:8000/api/ws/videos/{video_id}?ticket=...
```

Tickets have a 60-second TTL, allow exactly one connection, and an invalid ticket closes the socket with code `4401`.

## Live cameras and replay streams

A stream is either a live source (`rtsp://`, `rtsps://`, `http(s)://`, `tcp://`) or an uploaded video replayed as if it were live.

1. **Streams → Add**: give it a name and URL. Embedding `user:pass@` in the URL is rejected — this release stores no camera credentials.
2. **Start** the stream; the session connects, reads frames and publishes annotated JPEGs.
3. **Snapshot** captures a frame you can calibrate on; **Calibrate bays** lets you draw polygons on it.
4. The viewer connects to `WS /api/ws/streams/{id}` with a minted ticket and receives annotated frames, labelled `live` or `replay`, plus a `stale` warning if frames stop arriving.

Notes:

- Camera URLs pass an SSRF guard: schemes are allowlisted, metadata-service hosts are blocked, every resolved address of a hostname is validated (DNS-rebinding defence), and private ranges are rejected unless covered by `PARKWISE_TRUSTED_CAMERA_CIDRS`.
- Overcrowding on a calibrated stream fires the configured webhook. Webhook delivery refuses HTTP redirects, and the signing secret is only ever readable as a configured/not-configured boolean.
- Streams are isolated per operator session; stopping a stream releases its worker.

## How the pipeline works

`backend/app/services/video_pipeline.py` is the core. In order:

1. **Inspect** (`inspect_video`): OpenCV opens the file, reads the first frame for a preview, and reads real width, height, FPS and frame count. Unreadable files fail loudly instead of producing a fake preview.
2. **Detect + track**: YOLO runs restricted to the COCO vehicle classes — car (2), motorcycle (3), bus (5), truck (7) — with ByteTrack assigning persistent IDs across frames.
3. **Multi-scale recovery** (`_scale_candidates`, `_merge_vehicle_boxes`): when a frame reports fewer than `MULTISCALE_MIN_VEHICLES` (5) at the configured size, the same frame is re-run at 2560 px and at native resolution. The higher-resolution detections are merged with the primary set, so a genuinely empty lot still reports 0 rather than being "filled in".
4. **Per-bay matching** (`_space_states`): each vehicle box is tested against the normalized polygons you drew. A short per-space history (`deque`) debounces flicker so a bay does not flip state on a single noisy frame. Without geometry, no slot state is recorded — occupancy stays `unknown`.
5. **Persist**: one `DetectionSample` per processed frame (count, confidence, timestamp) and one `OccupancySample` per bay transition.
6. **Render output**: an annotated H.264 MP4 (via `ffmpeg`, falling back to the bundled `imageio-ffmpeg` binary) plus preview frames.
7. **Notify**: progress is published to `WS /api/ws/videos/{id}`, an activity event is recorded, and the webhook fires if configured.

Job states progress through `queued → processing → completed` or `failed`, with a bounded error message stored on the job.

## Real footage used for the public-source picker

The source catalogue uses direct MP4 locations resolved from Pexels' public download pages. They are downloaded only when an operator clicks **Fetch**. Please re-check applicable terms before redistribution or commercial use; footage is credited to its creator in the UI and source registry.

1. [Tom Fisk — Aerial Footage Of Cars On A Parking Lot](https://www.pexels.com/video/aerial-footage-of-cars-on-a-parking-lot-3848792/) — 38 seconds, 3840×2160, 29.97 FPS. Direct file URL in `backend/app/services/public_sources.py`.
2. [Yasin Koçtepe — An aerial view of a parking lot with cars](https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-27832493/) — 18 seconds, 3840×2160, 50 FPS.
3. [David Pickup — An aerial view of a parking lot with cars](https://www.pexels.com/video/an-aerial-view-of-a-parking-lot-with-cars-28125313/) — 31 seconds, 3840×2160, 29.97 FPS.

The project archive does not bundle these large third-party videos. The app fetches the real sources from their listed URLs when run in an internet-connected environment, and also accepts your own files.

## Architecture

```text
Public Pexels MP4 / permitted upload / RTSP camera URL / replayed upload
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
PARKWISE_AI/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI app, lifespan, CORS, startup safety checks
│   │   ├── config.py            # pydantic-settings configuration
│   │   ├── database.py          # engine, SessionLocal, init_db
│   │   ├── models.py            # SQLAlchemy tables
│   │   ├── schemas.py           # Pydantic request/response models
│   │   ├── security.py          # auth, RBAC, rate limiting, SSRF guard
│   │   ├── api/
│   │   │   ├── routes.py        # videos, public sources, health, config, analytics
│   │   │   ├── live.py          # live streams + frame WebSocket
│   │   │   ├── insights.py      # dashboard analytics, activity
│   │   │   ├── admin.py         # settings, users, billing, integrations, system info
│   │   │   └── ws_tickets.py    # single-use WebSocket tickets
│   │   └── services/
│   │       ├── video_pipeline.py      # inspection, detection, tracking, rendering
│   │       ├── live_stream.py         # stream sessions, frame manager
│   │       ├── public_sources.py      # Pexels catalogue + fetcher
│   │       ├── model_store.py         # weights loading and caching
│   │       ├── settings_store.py      # runtime-editable settings
│   │       ├── integrations.py        # webhook delivery
│   │       ├── billing.py             # local plan quotas
│   │       └── activity.py            # event feed
│   ├── tests/                 # pytest suite
│   └── Dockerfile
├── web/                       # Next.js App Router / TypeScript / CSS
│   ├── app/                   # layout, landing page, dashboard, styles
│   ├── components/            # charts, map/stream UI, shared UI
│   ├── lib/data.ts            # typed API client, error types, timeouts
│   └── Dockerfile
├── data/                      # runtime data only; excluded from git except .gitkeep
├── docs/                      # architecture, model guide, API and security notes
├── scripts/                   # run_local.sh, bootstrap_admin.py, check_project.py
├── docker-compose.yml
└── .github/workflows/         # CI, CodeQL
```

## API outline

- `GET /api/health`
- `GET /api/config/public`
- `GET /api/public-sources`, `POST /api/public-sources/{source_id}/fetch`
- `GET /api/dashboard/summary`, `GET /api/dashboard/analytics`
- `GET /api/activity`
- `GET /api/videos`
- `POST /api/videos/upload` — multipart field `file`
- `GET /api/videos/{video_id}`
- `DELETE /api/videos/{video_id}` — removes the job, its samples, calibration and media files
- `POST /api/videos/{video_id}/process` — returns `202`; runs in the background
- `GET /api/videos/{video_id}/preview`
- `GET /api/videos/{video_id}/original`
- `GET /api/videos/{video_id}/annotated`
- `GET /api/videos/{video_id}/spaces`
- `POST /api/videos/{video_id}/spaces`
- `DELETE /api/videos/{video_id}/spaces/{space_id}`
- `GET /api/videos/{video_id}/analytics`
- `GET /api/videos/{video_id}/occupancy` — per-bay free/occupied history from the last run
- `POST /api/videos/{video_id}/ws-ticket` — single-use ticket for the job-progress WebSocket
- `WS /api/ws/videos/{video_id}`
- `GET /api/streams`, `POST /api/streams`, `GET/PATCH/DELETE /api/streams/{stream_id}`
- `POST /api/streams/{stream_id}/start|stop|snapshot`, `PUT /api/streams/{stream_id}/spaces`
- `GET /api/streams/{stream_id}/snapshot`, `GET /api/streams/{stream_id}/events`
- `POST /api/streams/{stream_id}/ws-ticket`, `WS /api/ws/streams/{stream_id}` — annotated frames
- `GET/PUT /api/settings`, `POST /api/integrations/webhook/secret`, `POST /api/integrations/webhook/test`
- `GET/POST /api/users`, `PATCH/DELETE /api/users/{user_id}`, `POST /api/users/{user_id}/rotate-key`
- `GET/PUT /api/billing`
- `GET /api/system/info`

Full interactive schemas are available at `/docs`. Role gates: video/stream mutations need `admin` or `operator`; user, billing and settings administration needs `admin`. Mutating routes are rate-limited.

### Example: upload and analyze from the shell

```bash
# Upload
curl -H "X-API-Key: pk_..." -F "file=@lot.mp4" http://localhost:8000/api/videos/upload

# Add a bay (normalized 0–1 coordinates, max 30 points)
curl -H "X-API-Key: pk_..." -H "Content-Type: application/json" \
  -X POST http://localhost:8000/api/videos/{id}/spaces \
  -d '{"name":"Bay 01","points":[[0.10,0.20],[0.22,0.20],[0.22,0.35],[0.10,0.35]]}'

# Analyze (202 Accepted, runs in background)
curl -H "X-API-Key: pk_..." -X POST http://localhost:8000/api/videos/{id}/process

# Read results
curl -H "X-API-Key: pk_..." http://localhost:8000/api/videos/{id}/analytics
curl -H "X-API-Key: pk_..." http://localhost:8000/api/videos/{id}/occupancy
```

## Data model

All tables are defined in `backend/app/models.py`:

| Table | Purpose |
| --- | --- |
| `video_jobs` | One per uploaded/fetched video: filename, real duration/resolution, status, progress, error, output paths. |
| `parking_spaces` | Normalized polygons belonging to a video (bays). |
| `detection_samples` | Per-frame vehicle count and confidence series. |
| `occupancy_samples` | Per-bay state history from an analysis run. |
| `streams` | Live/replay sources: URL, state, calibration polygons, last frame metadata. |
| `app_settings` | Runtime-editable key/value settings with validation. |
| `users` | API-key hashes, roles, active flag, display names. |
| `activity_events` | Operator and system events shown in the Activity feed. |

To back up a running instance, copy `data/` (SQLite file plus media folders) or use the `parkwise_data` Docker volume.

## Validation and tests

```bash
# with the venv activated (see "Run without Docker")
.venv/bin/python3 -m pytest -q
.venv/bin/python3 scripts/check_project.py
```

```bash
# frontend checks
cd web && npm run lint && npx tsc --noEmit && npm run build
```

The suite covers API health, empty-state honesty, source allowlisting, polygon validation, analytics metrics, auth/RBAC, rate limiting, SSRF guards, startup security, live streams, stream isolation and regressions. Model inference tests require an actual model cache and video and are intentionally separated from the fast suite. What has been verified on a live machine is recorded in [docs/BUILD_STATUS.md](docs/BUILD_STATUS.md).

## Troubleshooting

**`ModuleNotFoundError: OpenCV (cv2) is missing from this interpreter`**
You launched a `uvicorn` that is not the venv's. Check with `which uvicorn` (must print `.venv/bin/uvicorn`) or just use `.venv/bin/python3 -m uvicorn app.main:app --app-dir backend`. `hash -r` clears a stale shell lookup.

**Dashboard says "API offline" but the terminal shows no error**
Nothing is listening on the port. Confirm with `curl http://127.0.0.1:8000/api/health` — `000` means connection refused. Start the API with the venv interpreter and reload the tab: an open dashboard holds its last failed state until it polls again.

**Dashboard says "API offline" while `/api/health` works in a browser tab**
Check the exact URL in `web/.env.local`. `NEXT_PUBLIC_*` is baked in at compile time, so restart `next dev` after changing it. If you opened the UI at a non-loopback hostname, add that origin to `PARKWISE_ALLOWED_ORIGINS` and restart the API.

**CORS errors mentioning an origin not in the allowlist**
Add it to `PARKWISE_ALLOWED_ORIGINS` (comma-separated, no trailing slash) and restart. Production refuses to start if this contains `*`.

**`docker compose up` — web container exits or shows offline**
The `web` service waits for the `api` healthcheck. If the API build failed (usually a torch/opencv wheel issue), fix the `api` container first; inspect with `docker compose logs api`.

**Analysis finishes suspicious fast with 0 vehicles**
Aerial footage can shrink a vehicle to a few pixels. Check `PARKWISE_IMAGE_SIZE` and keep `PARKWISE_MULTISCALE=true`; the pipeline reports a measured 0 rather than estimating. See [docs/AI_MODELS.md](docs/AI_MODELS.md).

**Occupancy shows `unknown`**
You have not calibrated bays for that video. Draw polygons, then re-run **Analyze with these bays**.

**Upload rejected**
Exceeding `PARKWISE_MAX_UPLOAD_MB` or `PARKWISE_MAX_VIDEO_SECONDS`, or an extension outside the allowlist. Raise the limit or convert the file.

**Requests return `401` / `403`**
`401` means `PARKWISE_AUTH_REQUIRED=true` and no valid key — add it in the dashboard (Settings → Users, stored for the tab). `403` means your role is insufficient.

**WebSocket closes with code `4401`**
The ticket is expired (60 s), already used, or was not minted over authenticated REST.

**Camera rejected as "SSRF"**
Private ranges require `PARKWISE_TRUSTED_CAMERA_CIDRS` covering that network; embedded credentials are never accepted.

## Deployment notes

- **Set `PARKWISE_ENV=production` and `PARKWISE_AUTH_REQUIRED=true`.** Production startup fails closed if auth is off or CORS has a wildcard.
- **Use PostgreSQL.** SQLite is fine for a local pilot; install a Postgres driver (`psycopg`) and point `PARKWISE_DATABASE_URL` at the managed instance.
- **Terminate TLS** in front of the API and set `NEXT_PUBLIC_API_BASE_URL` to the public HTTPS origin (no trailing slash). Append the dashboard's origin to `PARKWISE_ALLOWED_ORIGINS`.
- **Persist `/srv/data`** (video media and SQLite) on a volume with capacity for uploads and processed output.
- **Health check** `/api/health`; the Compose file already uses it for `depends_on`.
- **Still required before public exposure:** a durable job queue, object storage, retention automation, tenant isolation, monitoring/alerting, backups, secret rotation and a privacy review. See [docs/SECURITY.md](docs/SECURITY.md) and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).

## Performance expectations

On CPU, expect roughly 1–2 minutes for a short 1080p clip and about 30 minutes for the 38 s 4K public clip with multi-scale enabled. Progress is shown in the dashboard while the job runs.

Practical levers, in order of impact:

1. `PARKWISE_FRAME_STRIDE` — raise it (e.g. `6`) to halve the frames analyzed.
2. `PARKWISE_MULTISCALE=false` — biggest saving on long 4K clips; risks under-counting small vehicles.
3. `PARKWISE_IMAGE_SIZE` — lower to `960` for speed at the cost of small-object recall.
4. `PARKWISE_MODEL` — `yolo26n.pt` is markedly faster than `yolo26s.pt`.
5. `PARKWISE_DEVICE=cuda` — by far the largest gain if you have a supported GPU.

Inference runs as a FastAPI background task; a restart interrupts an in-flight job, which will show as failed and can be re-run.

## Privacy and safety

Parking footage can contain faces, plate numbers, staff and visitor activity. Obtain appropriate notices/permissions, define purpose and retention, restrict operator access, and minimize collection. This release does **not** perform license plate recognition and does not store plate text. Do not use it for enforcement decisions without legal and privacy review. Full baseline: [docs/SECURITY.md](docs/SECURITY.md).

## Limitations / next production steps

- A stock clip is recorded footage, not a live camera, and does not certify a real parking site's availability. Use a camera you control for operational decisions.
- Polygon matching is a baseline: calibrate fixed camera views, validate in day/night/weather and occlusion conditions, and measure precision/recall against labelled ground truth before using it operationally.
- Extreme aerial zoom-out can shrink a vehicle to a few pixels; even native-resolution inference may then report 0 for a frame. The pipeline records the measured 0 instead of estimating a count.
- Occupancy is **unknown** when there is no calibrated space geometry; no free-space count is estimated from a raw vehicle total.
- This release is single-tenant and intended for local pilots. API-key auth/RBAC and rate limiting are included, but add managed Postgres, object storage, a durable queue, tenant isolation, retention automation, and observability before exposing it publicly.
- Billing is a local simulation of plan quotas (`billing_mode: "local_simulation"`); no payment processor is connected.
- Ultralytics package/model licensing is deployment-dependent; review `docs/AI_MODELS.md` and obtain the appropriate license if needed.

## Contributing

1. Create a branch and make a focused change.
2. Run the backend suite and the frontend checks (see [Validation and tests](#validation-and-tests)).
3. Keep the empty-state contract: never seed demo rows, never hard-code KPIs.
4. Add tests for behavior changes; update the relevant `docs/` page when you change configuration, endpoints or security posture.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the short version.

## Documentation index

| Document | Contents |
| --- | --- |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Component boundaries and data flow. |
| [docs/API.md](docs/API.md) | Endpoint reference beyond the summary above. |
| [docs/AI_MODELS.md](docs/AI_MODELS.md) | Model choices, licensing, device setup. |
| [docs/DATA_SOURCES.md](docs/DATA_SOURCES.md) | Public footage catalogue and terms. |
| [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) | Deployment guidance. |
| [docs/SECURITY.md](docs/SECURITY.md) | Security and privacy baseline. |
| [docs/BUILD_STATUS.md](docs/BUILD_STATUS.md) | What has been verified on a live machine. |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Planned work. |
| [docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md) | Implementation notes. |

## License

This repository's source code is MIT-licensed under `LICENSE`. Third-party model weights, videos, and dependencies remain subject to their own terms. A repository-level MIT license does not override those terms.
