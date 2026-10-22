# Architecture and runtime boundaries

## Release scope

This release is a locally deployable video analytics pilot. It is video-driven: imported uploads and the curated public-video picker create `VideoJob` records; they do not connect to a live camera. A future camera adapter should use authenticated RTSP/ONVIF configuration, egress restrictions, reconnect policies and a durable work queue.

## Components

- **Next.js App Router + React + TypeScript** renders the operator experience. The browser reads actual values from FastAPI. Dashboard summary cards show an em dash (`—`) when no measured value exists.
- **FastAPI** validates uploads, exposes video lifecycle endpoints and WebSocket job status, serves previews/output media, and generates OpenAPI docs.
- **OpenCV** verifies video readability, extracts a first-frame preview, samples frames, draws annotations and writes an output video.
- **Ultralytics YOLO** detects COCO vehicle classes (car, motorcycle, bus, truck). ByteTrack is enabled for track ID continuity. The default configured model is `yolo26s.pt`; weights are fetched by Ultralytics at inference time if not cached. When a frame yields almost no vehicle detections at the configured image size, the pipeline re-runs that frame at 2560 px and native resolution (`PARKWISE_MULTISCALE`) before recording a count.
- **Space matching** compares detected vehicle centers against operator-drawn normalized polygon ROIs. A five-observation deque reduces brief state flicker. This is a baseline heuristic and should be validated for every camera angle.
- **SQLAlchemy** persists videos, per-frame detection samples, polygon definitions and per-space occupancy samples. SQLite is default for local use.

## Lifecycle

1. Upload or fetch an approved public MP4.
2. Inspect metadata and a real first-frame JPEG; keep job state `uploaded`.
3. Operator draws bay polygons if slot-level occupancy is required.
4. Operator starts inference; previous samples for that job are deleted before a rerun.
5. A worker processes every configured Nth frame. The annotated video is sampled at adjusted FPS to approximately preserve clip duration.
6. Frame-level detection data and slot states are stored as measurements.
7. Dashboard requests the summary, video jobs and analytics endpoints. A WebSocket emits job status/progress until completion/failure.

## Operational caveats

The initial worker uses FastAPI background tasks, which are not a durable queue. A process restart may interrupt a job; multi-user/commercial deployment should move inference into Celery/RQ/Arq or a dedicated worker service backed by Redis/RabbitMQ. The API has no user authentication in this pilot and must not be exposed to the public internet without an auth, authorization, upload-quota, retention and tenant-isolation layer.
