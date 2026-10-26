# Roadmap

## Pilot (current repository) — delivered

- Video upload and curated public-source fetch
- Vehicle detection/tracking with annotated output
- User-drawn polygon calibration and slot-state estimates (videos and live streams, ≤30 vertices)
- Measured analytics, persisted samples and processing progress (REST + ticketed WebSocket)
- Live/replay streams: RTSP/HTTP camera URL or replayed upload, per-stream models, reconnect with
  capped backoff, calibration snapshots, stale detection, overcrowding webhook
- API-key auth with `admin`/`operator`/`viewer` roles, rate limiting, production fail-closed startup
- Local plan simulation with video/stream/storage quotas

## Operational pilot

- Move jobs to a durable Redis-backed worker queue (background tasks are interrupted by a restart)
- Evaluate fixed camera feeds using labelled data and error budgets
- Add schedule-based retention/telemetry and richer camera health state
- Support H.264/AV1 media output consistently and large object storage
- Camera credential storage (today embedded `user:pass@` is rejected on purpose)

## Commercial facility platform

- Multi-site/tenant isolation, Postgres/PostGIS, migrations and full audit trail
- Camera-to-layout mapping, zones/lanes, entrance/exit line crossing and lane blockage rules
- Alert policies with delivery integrations and acknowledgement workflows
- Occupancy trend and demand forecasting after sufficient verified historical data
- Metered billing, customer support tooling and operational SLA controls

## Future/optional modules

- Reservation and payment integrations (requires availability synchronization and transactional safeguards)
- License plate recognition only with documented legal basis, retention, access controls and accuracy review
- Dynamic pricing only after demand models and business rules are validated; human operators approve price changes
- Edge packaging on NVIDIA Jetson/TensorRT after exporting and benchmarking the chosen model on target hardware

AI-generated forecasts or pricing are not included in the current release because a fresh
installation has no validated historical training data.
