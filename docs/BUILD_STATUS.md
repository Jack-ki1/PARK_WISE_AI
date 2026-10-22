# Build and verification status

Verification performed on an internet-connected Linux dev machine (Python 3.12 venv, Node 24):

- Python application files compile (`python3 -m compileall`); repository check script passes.
- FastAPI backend test suite passes (16 tests): the original API/validation tests plus coverage for `DELETE /api/videos/{id}` (record, cascade and on-disk cleanup, `404`, `409` while processing) and `GET /api/videos/{id}/occupancy` (empty, populated, `404`).
- Next.js production build, `tsc --noEmit`, and `eslint` complete with 0 errors (2 `next/no-img-element` warnings remain by design: preview URLs point at a runtime-configurable API origin, which `next/image` cannot optimize without per-deployment `remotePatterns`).
- Backend and dashboard run together without Docker (`scripts/run_local.sh` or the two-terminal commands in the README); `/api/health`, `/api/dashboard/summary`, `/api/config/public`, `/api/public-sources`, and the rendered dashboard HTML were checked live.
- Video deletion was exercised against the live API: multipart upload → space polygon → `GET .../occupancy` (empty) → `DELETE /api/videos/{id}` (`204`), after which the job was `404`, the media files were gone from `data/`, and the list count was unchanged. Re-deleting and reading occupancy of the removed id both return `404`.
- Light theme: every colour literal in `globals.css` was rewritten to a CSS variable with a curated light counterpart in `:root[data-theme="light"]`, plus a top-bar toggle and a pre-paint bootstrap script in `layout.tsx`. The palette was validated programmatically (0 same-rule colour pairs under 3:1 contrast in either theme; the only remaining bright-on-bright pairs are white labels on violet buttons/brand tiles, which are intentional). Serve the dashboard to confirm the rendered result.
- Public-source fetch of the Tom Fisk Pexels clip (3840×2160, 1135 frames, ~112 MB) succeeded through `POST /api/public-sources/{id}/fetch`.
- End-to-end analysis of that clip produced 379 stored samples with 0–223 detected vehicles per sampled frame (mean 52.8, mean confidence 0.545), an updated preview, and a browser-playable H.264 `*_annotated.mp4` (109 MB).
- A second operator-uploaded 4K clip completed with a peak of 268 observed vehicles in a frame.
- Upload (`multipart`), video inspection, space create/list/delete, analytics, and `WS /api/ws/videos/{id}` progress streaming were exercised against the running API.
- H.264 conversion was verified using the `imageio-ffmpeg` bundled ffmpeg binary, because this host has no system `ffmpeg`.

Not verified in this environment:

- A complete `docker compose up --build` launch: the Docker CLI exists, but WSL integration is disabled for this distribution.
- Automated browser click-through: the bundled headless Chromium cannot start here (missing system libraries such as `libnspr4`, no passwordless sudo). The dashboard was validated through its server-rendered HTML, its compiled stylesheet and API responses instead — so the light theme has not been viewed in a real browser on this machine.
- Per-bay occupancy over a full analysis run (the spaces API, the `GET .../occupancy` reader and the stored rows were exercised; the polygon state path itself was not run end to end on a calibrated clip).
- GPU inference.

Measured cost: analyzing the 38 s 4K public clip on CPU took about 30 minutes with `PARKWISE_MULTISCALE=true` (yolo26s at 1280 px, plus 2560/native passes on frames that otherwise report no vehicles). Raise `PARKWISE_FRAME_STRIDE` or set `PARKWISE_MULTISCALE=false` to trade accuracy for speed.

When run on an internet-connected development machine, `docker compose up --build` installs the frontend/backend dependencies. The first analysis may download the configured YOLO weights. The **Fetch public footage** actions obtain actual videos from the original Pexels URLs at runtime. If provider URLs or licenses change, use the linked source page or upload a video you are authorized to process.
