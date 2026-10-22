# API quick reference

Base URL: `http://localhost:8000`. Full OpenAPI schemas are served at `/docs`.

## Health and read APIs

```http
GET /api/health
GET /api/config/public
GET /api/public-sources
GET /api/dashboard/summary
GET /api/videos
GET /api/videos/{video_id}
GET /api/videos/{video_id}/analytics
GET /api/videos/{video_id}/occupancy
GET /api/videos/{video_id}/spaces
```

`GET /api/videos/{video_id}/occupancy` returns the stored per-bay history of the last analysis run
(`items[]` with `space_id`, `space_name`, `timestamp_seconds`, `state`, `confidence`), ordered by time.
It is empty until a video with calibrated polygons has been analyzed.

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

Create a space polygon using normalized x/y coordinates between 0 and 1:

```bash
curl -X POST http://localhost:8000/api/videos/VIDEO_UUID/spaces \
  -H 'Content-Type: application/json' \
  -d '{"name":"A-01","polygon":[[0.14,0.22],[0.20,0.21],[0.21,0.36],[0.14,0.37]]}'
```

The sample polygon above is only an API-shape example, not real calibration data; draw actual bay coordinates in the UI for your own camera.

## Deleting an imported video

```bash
curl -X DELETE http://localhost:8000/api/videos/VIDEO_UUID
```

Returns `204` and removes the job row plus its spaces, detection samples, occupancy samples and every
derived file on disk (original, preview, annotated output). A queued or processing job answers `409`;
wait for it to finish or fail first.

## Media and live status

```http
GET /api/videos/{video_id}/preview
GET /api/videos/{video_id}/original
GET /api/videos/{video_id}/annotated
WS  /api/ws/videos/{video_id}
```

`GET /api/dashboard/summary` returns null measurements where no measured record exists. Occupancy percentage is only returned when the latest video's spaces have classified states.
