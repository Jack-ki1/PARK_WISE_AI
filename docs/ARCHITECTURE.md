# Architecture and runtime boundaries

## Release scope

This release is a locally deployable video analytics pilot with two source kinds:

- **Recorded video** — imported uploads and the curated public-video picker create `VideoJob`
  records that are analysed offline frame-by-frame.
- **Live/replay streams** — a `Stream` points at an RTSP/HTTP camera URL (`source_mode:
  live_camera`) or an uploaded video played back in real time (`source_mode: replay`). Each running
  stream owns a background session that decodes frames, runs detection per stream, publishes
  annotated frames over WebSocket and keeps a recent snapshot for calibration. A real RTSP camera
  still has to be supplied and validated by the operator; embedded URL credentials are rejected and
  private ranges need `PARKWISE_TRUSTED_CAMERA_CIDRS`.

## Components

- **Next.js App Router + React + TypeScript** renders the operator experience (Dashboard, Live
  View, Reports & Settings). The browser reads actual values from FastAPI; dashboard summary cards
  show an em dash (`—`) when no measured value exists.
- **FastAPI** validates uploads, exposes video/stream lifecycle endpoints, WebSocket job status and
  frame streaming (ticket-gated), serves previews/output media, enforces API-key RBAC and rate
  limits, and generates OpenAPI docs.
- **OpenCV** verifies video readability, extracts a first-frame preview, samples frames, draws
  annotations and writes an output video; it also decodes live/replay stream frames.
- **Ultralytics YOLO** detects COCO vehicle classes (car, motorcycle, bus, truck). ByteTrack is
  enabled for track ID continuity. The default configured model is `yolo26s.pt`; weights are
  fetched by Ultralytics at inference time if not cached. When a frame yields almost no vehicle
  detections at the configured image size, the recorded-video pipeline re-runs that frame at 2560 px
  and native resolution (`PARKWISE_MULTISCALE`) before recording a count. Streams use a per-stream
  model instance so tracker state is never shared between cameras.
- **Space matching** compares detected vehicle centers against operator-drawn normalized polygon
  ROIs (max 30 vertices). A five-observation deque reduces brief state flicker. This is a baseline
  heuristic and should be validated for every camera angle.
- **SQLAlchemy** persists videos, streams, per-frame detection samples, polygon definitions,
  per-space occupancy samples, users/API-key hashes and audit events. SQLite is default for local
  use.
- **`StreamManager`** starts/stops stream sessions, tracks WebSocket subscribers (a stream stays up
  while an operator explicitly started it), serves the latest frame to new subscribers and drops
  per-stream models on stop.

## Lifecycle

### Recorded video
1. Upload or fetch an approved public MP4.
2. Inspect metadata and a real first-frame JPEG; keep job state `uploaded`.
3. Operator draws bay polygons on the preview if slot-level occupancy is required.
4. Operator starts inference; previous samples for that job are deleted before a rerun.
5. A background task processes every configured Nth frame. The annotated video is sampled at
   adjusted FPS to approximately preserve clip duration.
6. Frame-level detection data and slot states are stored as measurements; the dashboard polls and
   receives WebSocket progress until completion/failure.
7. Deleting the video removes the job, its samples, calibration polygons, and every derived file on
   disk; any stream that used it as a replay source is detached and stopped.

### Live/replay stream
1. Operator creates a stream (camera URL or replay video), optionally with lat/lon for the site map.
2. Operator starts it explicitly; the session decodes at `target_fps` (≤15), runs the detector and
   publishes annotated frames. Live cameras reconnect with capped exponential backoff; replay
   videos end cleanly.
3. A calibration snapshot is captured, bays are drawn on it, and occupancy is published per bay.
4. Frame WebSockets use a single-use ticket; the UI shows live vs replay honestly plus a stale
   banner when frames stop arriving.
5. Overcrowding on a calibrated stream fires the configured `stream.overcrowding` webhook.

## Operational caveats

The initial worker uses FastAPI background tasks, which are not a durable queue. A process restart
may interrupt a job; multi-user/commercial deployment should move inference into Celery/RQ/Arq or a
dedicated worker service backed by Redis/RabbitMQ. Auth/RBAC, rate limiting, ticketed WebSockets
and production fail-closed startup are included, but tenant isolation, TLS termination, object
storage and retention automation are not — the deployment must stay behind a trusted network until
those exist.
