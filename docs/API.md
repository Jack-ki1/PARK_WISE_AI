# API quick reference

Base URL: `http://localhost:8000`. Full OpenAPI schemas are served at `/docs`.

## Authentication and roles

Send `Authorization: Bearer pk_…` or `X-API-Key: pk_…` on REST calls. Keys are issued under
Reports & Settings → Users; roles are `admin`, `operator`, `viewer`.

- With `PARKWISE_AUTH_REQUIRED=true` every request needs a key.
- With it `false` (local development), anonymous requests are allowed but a presented key is still
  role-checked: video/stream mutations require `admin`/`operator`, user and billing administration
  requires `admin`.
- WebSockets never take a durable key in the URL. Mint a single-use ticket first
  (`POST /api/streams/{id}/ws-ticket`, `POST /api/videos/{id}/ws-ticket`; 60 s TTL) and connect to
  `…?ticket=TICKET_VALUE`. Invalid or reused tickets are closed with code 4401.
- Mutating endpoints are rate limited (`PARKWISE_RATE_LIMIT_PER_MINUTE`).

## Health and read APIs

```http
GET /api/health
GET /api/config/public
GET /api/public-sources
GET /api/dashboard/summary
GET /api/system/info
GET /api/settings
GET /api/activity
GET /api/users
GET /api/billing
GET /api/videos
GET /api/videos/{video_id}
GET /api/videos/{video_id}/analytics
GET /api/videos/{video_id}/occupancy
GET /api/videos/{video_id}/spaces
GET /api/streams
GET /api/streams/{stream_id}
GET /api/streams/{stream_id}/events
```

`GET /api/videos/{video_id}/occupancy` returns the stored per-bay history of the last analysis run
(`items[]` with `space_id`, `space_name`, `timestamp_seconds`, `state`, `confidence`), ordered by
time. It is empty until a video with calibrated polygons has been analyzed.

`GET /api/dashboard/summary` returns null measurements where no measured record exists, and an
`occupancy_percent` computed as occupied / (occupied + free) over the latest classified bays —
unknown states are excluded from the denominator rather than counted as free.

## Import and inference

Upload a permitted video as multipart `file`:

```bash
curl -F 'file=@parking-lot.mp4' http://localhost:8000/api/videos/upload
```

Fetch one of the registered Pexels sources (see `GET /api/public-sources`):

```bash
curl -X POST http://localhost:8000/api/public-sources/pexels-tom-fisk-3848792/fetch
```

Start analysis:

```bash
curl -X POST http://localhost:8000/api/videos/VIDEO_UUID/process
```

Create a space polygon using normalized x/y coordinates between 0 and 1 (max 30 points):

```bash
curl -X POST http://localhost:8000/api/videos/VIDEO_UUID/spaces \
  -H 'Content-Type: application/json' \
  -d '{"name":"A-01","polygon":[[0.14,0.22],[0.20,0.21],[0.21,0.36],[0.14,0.37]]}'
```

The sample polygon above is only an API-shape example, not real calibration data; draw actual bay
coordinates in the UI for your own camera.

## Deleting an imported video

```bash
curl -X DELETE http://localhost:8000/api/videos/VIDEO_UUID
```

Returns `204` and removes the job row plus its spaces, detection samples, occupancy samples and every
derived file on disk (original, preview, annotated output). Any stream using the video as a replay
source is stopped and detached so its `video_id` is cleared. A queued or processing job answers
`409`; wait for it to finish or fail first.

## Media, job progress and live streams

```http
GET  /api/videos/{video_id}/preview
GET  /api/videos/{video_id}/original
GET  /api/videos/{video_id}/annotated
POST /api/videos/{video_id}/ws-ticket
WS   /api/ws/videos/{video_id}          # 1 Hz job progress
```

Streams (RTSP/HTTP camera URL or replay of an uploaded video):

```bash
curl -X POST http://localhost:8000/api/streams \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lot A","kind":"url","url":"rtsp://192.168.1.10:554/stream","target_fps":6}'
```

```http
POST   /api/streams
GET    /api/streams
PATCH  /api/streams/{stream_id}
DELETE /api/streams/{stream_id}          # also deletes its calibration snapshot file
PUT    /api/streams/{stream_id}/spaces   # replace bay polygons
POST   /api/streams/{stream_id}/snapshot  # capture a calibration frame
POST   /api/streams/{stream_id}/start
POST   /api/streams/{stream_id}/stop
POST   /api/streams/{stream_id}/ws-ticket
WS     /api/ws/streams/{stream_id}       # annotated frames + status messages
```

Stream responses redact any URL userinfo (`url` is already display-safe), and report `source_mode`
(`live_camera`/`replay`), `running`, `stale`, `last_frame_age_seconds`, `frames_delivered` and
`subscriber_count`. Streams are billed against the active plan (video/stream/storage quotas);
`POST /api/billing` selects a plan and answers `402` when a limit is exceeded, `422` when the
request is invalid.

## Administration

```http
POST   /api/users                 # admin: creates a user, returns its API key once
PATCH  /api/users/{user_id}       # admin: role/active toggle
POST   /api/users/{user_id}/rotate-key
DELETE /api/users/{user_id}
GET/PUT /api/billing
GET/PUT /api/settings             # operator+
POST   /api/integrations/webhook/secret
```

`GET /api/settings` and `GET /api/billing` never return secret values — only booleans such as
`webhook_secret_configured`.
