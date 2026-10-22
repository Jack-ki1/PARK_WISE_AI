# Roadmap

## Pilot (current repository)

- Video upload and curated public-source fetch
- Vehicle detection/tracking with annotated output
- User-drawn polygon calibration and slot-state estimates
- Measured analytics, persisted samples and processing progress

## Operational pilot

- Add API authentication/RBAC and site/camera ownership
- Move jobs to a durable Redis-backed worker queue
- Evaluate fixed camera feeds using labelled data and error budgets
- Add camera health/staleness state, schedule retention and telemetry
- Support H.264/AV1 media output consistently and large object storage

## Commercial facility platform

- RTSP/ONVIF adapter with reconnect/backoff and secure network egress
- Multi-site/tenant isolation, Postgres/PostGIS, migrations and audit trail
- Camera-to-layout mapping, zones/lanes, entrance/exit line crossing and lane blockage rules
- Alert policies with delivery integrations and acknowledgement workflows
- Occupancy trend and demand forecasting after sufficient verified historical data
- Metered billing, customer support tooling and operational SLA controls

## Future/optional modules

- Reservation and payment integrations (requires availability synchronization and transactional safeguards)
- License plate recognition only with documented legal basis, retention, access controls and accuracy review
- Dynamic pricing only after demand models and business rules are validated; human operators approve price changes
- Edge packaging on NVIDIA Jetson/TensorRT after exporting and benchmarking the chosen model on target hardware

AI-generated forecasts or pricing are not included in the current release because a fresh installation has no validated historical training data.
