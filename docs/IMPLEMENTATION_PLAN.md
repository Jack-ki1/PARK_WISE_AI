# Implementation plan and release acceptance

## Release 1 — working video-analytics pilot (implemented in this archive)

- [x] Product concept, architecture, provenance, model evaluation and risk notes.
- [x] Python/FastAPI API, SQLAlchemy persistence and OpenAPI.
- [x] Actual video upload plus finite Pexels public-source fetch catalogue.
- [x] Metadata validation, real-frame preview extraction and file-size/duration limits.
- [x] YOLO vehicle detection + ByteTrack on sampled video frames.
- [x] User-drawn parking-bay polygons, temporal smoothing and per-space measurements.
- [x] Annotated output, confidence and vehicle-count samples, job progress and failure state.
- [x] Next.js dashboard, Video Lab, calibration editor, analytics view and job events.
- [x] REST and WebSocket interfaces, Docker Compose and tests.

### Acceptance checks

- A fresh database reports zero videos and null measured KPIs.
- Fetching/uploading a clip creates a job only after the file has been inspected.
- No analysis metrics are generated until an operator starts model inference.
- Inference failure records a visible failed job rather than returning fake counts.
- With no calibrated spaces, the dashboard does not present a free/occupied bay count.
- Calibrated spaces are tied to a specific source video/camera view and their states are model estimates.
- Re-running analysis clears old samples for that same clip to prevent duplicate analytics.

## Release 2 — site pilot hardening (recommended next)

1. Add login, role-based access control, per-site ownership and an audit log.
2. Replace FastAPI in-process background processing with a durable worker queue.
3. Add database migrations, PostgreSQL, object storage and retention jobs.
4. Build labelled ground-truth test sets by camera/site/time period; set acceptance thresholds for occupancy and false-free rate.
5. Add camera health, quality/staleness indicators and human feedback/correction tools.
6. Add exportable CSV reports and alert acknowledgement.

## Release 3 — live cameras and multi-site operations

1. Add a hardened RTSP/ONVIF camera adapter and secure network-egress policy.
2. Implement reconnect, backoff, offline buffering, frame-drop metrics and per-camera workers.
3. Use GPU/edge inference with device-specific benchmarking; export to TensorRT only after equivalence tests.
4. Add zone/lane geometry, entry/exit line crossing, blockage rules, and camera-to-layout calibration versioning.
5. Roll out to a limited site in shadow mode with an operator checking availability before driver-facing use.

## Release 4 — forecasting and commercial modules

- Forecast only after enough verified and time-stamped occupancy history has accumulated.
- Add reservations/payments only with transaction-safe allocation and integration contracts.
- Add ANPR/LPR only after legal, privacy, accuracy and retention reviews.
- Add dynamic pricing only as a human-approved recommendation until business outcomes are validated.
