# Build and verification status

Last verified: **2026-10-25** (session 7 — dashboard activity plots, Live Analysis mode split,
Settings cleanup; backend unchanged since session 5). Environment: internet-connected Linux dev
machine, Python 3.12 venv (`.venv`), Node 24, Next.js 16.4.2 (Turbopack).

## Verified on this machine

- **Backend tests: 107 passed** (`.venv/bin/python3 -m pytest backend/tests -q`) — the security
  suite (auth/roles, secret redaction, SSRF with trusted-CIDR allowlist and percent-encoded-credential
  rejection, `redact_url`, WebSocket tickets incl. wrong-stream and single-use), stream
  isolation/reconnect/staleness/tracker tests, insights metric tests, startup fail-closed security
  tests, plus the new `backend/tests/test_regressions.py` (role gates, delete cleanup, video
  ws-ticket single-use/scoping/expiry, dashboard occupancy maths, billing PUT shape, stream
  lifecycle). A `conftest.py` autouse fixture drops/recreates tables, shuts down the stream manager
  and clears rate-limit/ticket state between tests.
- **Repository check:** `python3 scripts/check_project.py` — 22 application files parsed, core files
  present.
- **Syntax:** `python3 -m compileall -q backend/app` — clean.
- **Frontend:** `npm run lint` — 0 errors (3 `next/no-img-element` warnings remain by design: preview
  URLs point at a runtime-configurable API origin that `next/image` cannot optimize without
  per-deployment `remotePatterns`). `npx tsc --noEmit` — clean. `npm run build` — OK.
  Design system (session 6): light-default bright palette with opt-in navy dark theme
  (`data-theme="dark"`), indigo→violet→cyan brand gradient, correct status semantics
  (occupied/over red, free green), Plus Jakarta Sans + JetBrains Mono via `next/font/google`
  (Geist uninstalled), component rules layered under Tailwind v4 (`@layer components`) with KPI,
  button, hero and chart overrides above. Served dev CSS verified to contain the Tailwind
  theme/base/utilities layers + preflight alongside the design tokens, zero legacy font references;
  the dev server had to be restarted once because a process started before `postcss.config.mjs`
  existed logged `Unknown at rule: @theme` instead of compiling Tailwind. Charts were rewritten on
  Recharts 3 (sparkline/area/line/donut) and themed through CSS `currentColor`/tokens.
- **Session 7 UI rework:** dashboard now shows 8 charts in 4 pairs (daily actions, video-status
  donut, bay-state donut, activity-by-user `HBarChart`, action-share `ShareBar`, confidence-by-
  analysis bars, vehicles-per-analysis trend, stream-health donut) with the occupancy-trend card
  and audit panel removed; **Live View became Live Analysis** with a live/recorded mode toggle,
  a client-side SVG bay overlay (green flicker free / red occupied, colours matched to the
  server's `_annotate`), a three-panel findings/bay-states/frame-metrics row, re-annotation for
  both modes, and authenticated annotated-video download (`X-API-Key` blob fetch) plus live
  `MediaRecorder` webm capture; **Settings lost the Reports tab entirely** and gained model
  runtime presets with unsaved-change markers, webhook/source status chips, user search with a
  Last seen column, billing usage facts with ≥80% meter warnings and extra system rows. New CSS
  lives inside `@layer components`. Verified: tsc clean, lint 0 errors, build OK, 107 backend
  tests pass, served dev CSS contains all 15 new style groups with zero parse warnings.
- **Production safety:** with `PARKWISE_ENV=production`, startup aborts (`RuntimeError`) if
  `PARKWISE_AUTH_REQUIRED=false` or `PARKWISE_ALLOWED_ORIGINS` contains a wildcard; a warning is
  logged if auth is off and the API binds a non-loopback interface.
- **Security fixes verified by tests, not just code inspection:**
  - `GET /api/settings` returns `webhook_secret_configured: boolean`, never the secret; rotation/
    creation only via `POST /api/integrations/webhook/secret`.
  - WebSocket authentication is ticket-only (`POST /api/streams/{id}/ws-ticket` and now
    `POST /api/videos/{id}/ws-ticket`, 60 s TTL, single-use, close code 4401); the legacy
    durable-key `?key=` query parameter is rejected. A shared `ws_tickets` store backs both.
  - External URL validation resolves every DNS answer and blocks metadata-service and private
    ranges by default, with an explicit `PARKWISE_TRUSTED_CAMERA_CIDRS` CIDR allowlist for
    deliberately-segmented on-prem cameras; embedded `user:pass@` credentials are rejected (this
    release stores no camera credentials) and every returned stream URL is passed through
    `redact_url()`.
  - **Role gates (new):** video mutations (upload/process/delete/spaces) require
    `admin`/`operator`, as do stream mutations (create/patch/delete/spaces/snapshot/start/stop).
    Verified live: a real `viewer` key gets `403 {"detail":"Requires one of: admin, operator"}` on
    `POST /api/streams` and `DELETE /api/videos/{id}`, and `200` on reads.
  - Map popups are built with DOM `textContent` only (stream names containing HTML render as inert
    text).
  - Webhook delivery refuses HTTP redirects (`_NoRedirectHandler`), including the new
    `stream.overcrowding` event.
  - Billing runs after validation (422 before 402); responses carry `billing_mode:
    "local_simulation"`; `PUT /api/billing` now returns `videos_total` and the storage meter counts
    the `data/streams` folder.
  - Occupancy utilisation divides by occupied+free (unknown states excluded) on both the analytics
    and dashboard-summary paths; a valid `0.0` average confidence is preserved, not collapsed to
    null.
- **Live/stream correctness:** concurrent streams get isolated per-stream YOLO instances
  (`get_stream_model`, `INFERENCE_LOCK`); live camera streams reconnect with capped exponential
  backoff (`stream_max_reconnect_attempts`, jitter, ≤30 s) while replay videos end cleanly; streams
  expose `source_mode` / `stale` / `last_frame_age_seconds` and the dashboard labels replay clips
  **Replay** (never Live) and shows a stale banner when frames stop arriving. A stream started
  explicitly now keeps running after its last WebSocket viewer disconnects (`stop_if_idle` only
  applies to viewer-triggered starts).
- **Delete cleanup (new):** deleting a video removes the job, samples, calibration, original,
  preview **and** `{id}_annotated.mp4`, and clears `stream.video_id` on any stream that used it as a
  replay source (the stream itself survives). Verified live — no leftover files matched the deleted
  UUID anywhere under `data/`.
- **Admin attribution:** `create_user` / `patch_user` / `rotate_key` / `delete_user` record the
  acting admin correctly (no parameter shadowing).
- **Frontend auth storage:** the dashboard API key is kept in `sessionStorage` only
  (`parkwise-session-api-key`) and cleared with the tab; the webhook secret is never prefilled and
  is only writable through the dedicated secret endpoint.

## End-to-end evidence from this session (real media, live server)

- **Recorded-video path:** uploaded a 5 s 1080p clip (sourced from a permitted Pexels file), drew
  4 bay polygons through the API, ran inference (30.6 s, 50 samples, max 20 vehicles, avg conf
  0.69) and read back 200 occupancy points with genuine per-bay transitions (free/occupied/unknown)
  plus a playable H.264 annotated MP4.
- **Live/replay path:** served that clip as a live-paced HTTP source with ffmpeg
  (`-re -stream_loop -1 -listen 1`), created a live camera stream against it and received 38
  annotated frames over the ticketed WebSocket, a calibration snapshot, `PUT …/spaces` for bays,
  and per-stream events. Reconnect/backoff was observed climbing attempts 1 → 5 to a terminal
  error after the source was killed; a separate replay-kind stream delivered 29 frames with
  `source_mode: replay`.
- **Occupancy E2E (closed):** the calibrated-bay occupancy path now runs end to end on real
  footage, so the previously open item "calibrated occupancy E2E" is done. It is still *not*
  validated against human-labelled ground truth.
- Earlier session evidence still stands: multi-scale YOLO fix (measured 0 → 0–223 vehicles on a
  real 4K clip), H.264 conversion via `imageio-ffmpeg`, light theme + toggle, public-source fetch.

## Not verified in this environment (blocked or open)

- **Docker Compose launch** (`docker compose up --build`): the Docker CLI exists, but WSL
  integration is disabled for this distribution.
- **Automated browser click-through / screenshots:** headless Chromium *and* Firefox cannot start
  here (missing `libnspr4`/`libnss3`/`libasound.so.2`, no passwordless sudo), so the dashboard was
  validated through its server-rendered HTML, the compiled stylesheet served by the dev server, and
  API responses. Light theme, replay badges, stale banner, the polygon cap feedback and the
  users-panel 403 state have not been viewed in a real browser on this machine. **Run
  Playwright/screenshot QA on a host with working browser libraries.**
- **Real RTSP camera test:** no authorized camera source is available here. An operator with a
  real camera should verify: credential-free URL (embedded `user:pass@` is rejected),
  `PARKWISE_TRUSTED_CAMERA_CIDRS` if the camera sits on a private range, reconnect/backoff after a
  network drop, and the stale banner after a stalled stream.
- **Per-bay occupancy against manual ground truth:** the spaces API, `GET .../occupancy`, stored
  rows and a full calibrated run are exercised; the polygon state path has not been compared to
  human-labelled truth.
- **GPU inference.**

## Known open work (tracked, not hidden)

- Frontend App Router modularization: `web/app/page.tsx` is still a single ~1,780-line page
  (Phase 2).
- A role-based semantic CSS token redesign (beyond the current `--pw-cN` variable naming) is
  Phase 2; session 6 rebuilt the palette, typography and chart theming on top of those variables.

Measured cost: analyzing the 38 s 4K public clip on CPU took about 30 minutes with
`PARKWISE_MULTISCALE=true` (yolo26s at 1280 px, plus 2560/native passes on frames that otherwise
report no vehicles). Raise `PARKWISE_FRAME_STRIDE` or set `PARKWISE_MULTISCALE=false` to trade
accuracy for speed.

When run on an internet-connected development machine, `docker compose up --build` installs the
frontend/backend dependencies. The first analysis may download the configured YOLO weights. The
**Fetch public footage** actions obtain actual videos from the original Pexels URLs at runtime. If
provider URLs or licenses change, use the linked source page or upload a video you are authorized to
process.
