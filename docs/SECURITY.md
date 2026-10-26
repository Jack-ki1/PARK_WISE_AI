# Security and privacy baseline

## Included safeguards

- **API-key authentication.** Users are created under Reports & Settings → Users and receive a
  random `pk_…` key shown once. Requests authenticate with `Authorization: Bearer pk_…` or
  `X-API-Key`. With `PARKWISE_AUTH_REQUIRED=true` every request needs a key; with it `false`,
  anonymous access is allowed but a presented key is still honoured.
- **Role-based authorization (RBAC).** Roles are `admin`, `operator`, `viewer`. Video mutations
  (upload/process/delete/spaces), stream mutations (create/patch/delete/spaces/snapshot/start/stop),
  and user/billing administration each require an explicit role; a viewer is refused with `403`
  rather than silently doing nothing. The last active admin cannot be deleted or deactivated.
- **Ticket-gated WebSockets.** Browsers cannot attach an API-key header to a WebSocket handshake,
  so both the frame stream (`/api/ws/streams/{id}`) and the job-progress stream
  (`/api/ws/videos/{id}`) take a short-lived, single-use ticket minted over REST
  (`POST /api/streams/{id}/ws-ticket`, `POST /api/videos/{id}/ws-ticket`; 60 s TTL, one
  connection each, close code 4401 when invalid). Durable keys are never placed in a URL.
- **Rate limiting** on mutating endpoints (`PARKWISE_RATE_LIMIT_PER_MINUTE`, `0` disables).
- **SSRF protection for camera/webhook URLs.** Schemes are allowlisted (`rtsp`, `rtsps`, `http`,
  `https`, `tcp`), metadata-service hosts are blocked, every resolved address of a hostname is
  validated (DNS-rebinding defence), and private ranges are rejected unless listed in
  `PARKWISE_TRUSTED_CAMERA_CIDRS`. Embedded `user:pass@` credentials are rejected — this release
  stores no camera credentials. Returned stream URLs pass through `redact_url()`.
- **Webhook delivery** refuses HTTP redirects, and the signing secret is only readable as a
  configured/not-configured boolean.
- **Local billing quotas** (plan limits on videos/streams/storage) are enforced before work starts;
  responses are labelled `billing_mode: "local_simulation"` and no payment processor is connected.
- **Production fail-closed startup.** With `PARKWISE_ENV=production`, the process refuses to start
  when auth is off or `PARKWISE_ALLOWED_ORIGINS` contains a wildcard, and warns when auth is off on
  a non-loopback bind.
- File-extension allowlist and configurable byte limit for uploads; video paths are generated
  server-side from UUIDs (client file names are display metadata only).
- Normalized polygon input is validated and constrained to [0, 1] (max 30 vertices).
- CORS origins are configurable; defaults are local development origins.
- Error messages are persisted with a bounded length; stack traces belong in server logs.
- Map popups are built with DOM `textContent` only, so stream names containing markup render as
  inert text.
- Session API key in the dashboard is stored in `sessionStorage` only and disappears with the tab.

## Not included — required before internet exposure

- Durable asynchronous job queue (FastAPI background tasks are interrupted by a restart), managed
  object storage, antivirus/content scanning, media transcoding sandboxing and automatic
  retention/deletion.
- TLS termination, secret rotation, encrypted backup, database migrations, tenant/site isolation
  and SSO.
- Monitoring/alerts, log redaction pipelines, backup/restore drills and an incident response plan.

## Camera/video privacy

Parking footage can contain faces, plate numbers, staff and visitor activity. Obtain appropriate
notices/permissions, define purpose and retention, restrict operator access, minimize collection and
avoid using LPR/identity features until a privacy/legal review is complete. This release does not
perform license plate recognition and does not store plate text.
