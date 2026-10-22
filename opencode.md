# OpenCode session — ParkWise AI

Session date: 2026-10-22 · Repo: `v2_parkwise-ai` · Goal: *review the project in depth, make it work and run at the best level (use `python3`, never `python`)*.

---

## 1. What the project is

Video-driven parking intelligence stack:

- **backend/** — FastAPI + SQLAlchemy (SQLite default) + OpenCV/ Ultralytics YOLO detection with ByteTrack, background job processing, REST + WebSocket progress API.
- **web/** — Next.js App Router + TypeScript dashboard (Overview, Video Lab, Space Calibration, Analytics, Job Events, System).
- **data/** — runtime-only uploads/previews/processed artifacts (git-ignored).
- **docs/**, **scripts/**, **docker-compose.yml**, `.github/workflows/` (CI: pytest + `next build`).

Flow: fetch/upload a clip → OpenCV inspect (real metadata + preview frame) → optional per-bay polygons → `POST /process` → background worker (YOLO on sampled frames, polygon occupancy, annotated MP4) → samples persisted → dashboard/`/analytics`.

---

## 2. Environment brought up

| Step | Command / action |
|---|---|
| venv | `uv venv --python 3.12 .venv` (host `python3` is 3.14 → pinned to 3.12, the version the project recommends; every command uses `python3`/`.venv/bin/python3`) |
| Backend deps | `uv pip install --python .venv/bin/python -r backend/requirements.txt -r backend/requirements-test.txt` |
| Web deps | `cd web && npm install` (Node 24) |
| Config | `cp .env.example .env`, `web/.env.local` with `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000` |
| API running | `.venv/bin/python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000` → <http://localhost:8000> (`/docs`, `/api/health`) |
| Web running | `cd web && npm run dev` → <http://localhost:3000> |
| One-command launcher | new `scripts/run_local.sh` does the whole setup and starts both with `python3` |

---

## 3. Problem found and fixed: detections were always zero

**Symptom:** first end-to-end run of the real Pexels 4K clip "completed" but stored `vehicle_count = 0` for all 379 samples and `avg_confidence = null` — the dashboard advertised measured analytics while showing nothing measured.

**Root cause (measured, not guessed):** with the shipped defaults (`yolo26n.pt`, `imgsz=640`), COCO-trained models misclassify top-down aerial vehicles at that scale — boxes landed correctly on cars but labels came back `cell phone`/`keyboard`, so the `classes=[2,3,5,7]` filter dropped everything. Benchmarked on frames from the clip: `yolo26n@640 → 9 objects, 0 vehicles`; `yolo26s@1280 → 17–42 vehicles` on close-ups but still `0` on zoomed-out segments; native-resolution (3840) passes recovered 181–192 vehicles where smaller scales saw none.

**Fix — adaptive multi-scale inference** in `backend/app/services/video_pipeline.py`:

- `_scale_candidates(width)` → `[PARKWISE_IMAGE_SIZE, 2560, native]` (deduped for smaller sources).
- Each sampled frame runs the tracked pass at the configured size; if it yields `< 5` vehicle boxes (`MULTISCALE_MIN_VEHICLES`), the frame is re-inferred at 2560 px and then native resolution with `model.predict` (ByteTrack state untouched by fallback passes).
- `_merge_vehicle_boxes()` merges passes with class-wise `cv2.dnn.NMSBoxes`.
- New setting `PARKWISE_MULTISCALE` (default `true`) to opt out; exposed in `GET /api/config/public` and shown in the dashboard (System & Models).

**Defaults raised:** `PARKWISE_MODEL=yolo26s.pt`, `PARKWISE_IMAGE_SIZE=1280` (`.env.example`, `backend/app/config.py`).

**Result on the same clip:** 379 samples, 0–223 vehicles/frame (mean 52.8, mean confidence 0.545), peak 223; a second operator-uploaded 4K clip reached a peak of 268. Trailing frames of extreme zoom-out (vehicles a few pixels wide) still honestly report 0 — documented as a limitation rather than papered over.

---

## 4. Other fixes and improvements

- **Browser-playable output:** this host has no system `ffmpeg`, so annotated videos stayed as OpenCV `mp4v` (276 MB, won't play in browsers). Added `imageio-ffmpeg` to `backend/requirements.txt` and `_ffmpeg_executable()` (system ffmpeg → bundled binary). Output is now H.264 `*_annotated.mp4`, 109 MB, served as `video/mp4`; conversion timeout raised 240 s → 900 s for 4K.
- **Frontend lint errors fixed (4 → 0):**
  - `CalibrationCanvas`: `paint` used before declaration — `paint`/`paintRef` declared before the image-load effect, effect deps made exhaustive (removed an `eslint-disable`).
  - Two `react-hooks/set-state-in-effect` errors: per-video state (`spaces`, `analytics`, `pendingPoints`) converted from flat arrays to keyed maps (`spacesByVideo` etc.) with values derived from the selected id, so switching videos needs no synchronous `setState` in an effect; `refreshData` rewritten as a promise chain whose `setState` calls live only in async callbacks.
  - Removed 6 unused icon imports.
  - Remaining: 2 `@next/next/no-img-element` warnings — kept deliberately (preview URLs point at a runtime-configurable API origin that `next/image` can't optimize without per-deployment `remotePatterns`); documented in `docs/BUILD_STATUS.md`.
- **UX/config surfaced:** `multiscale` added to `PublicConfig` type, a System & Models row, and the settings callout env-var list.
- **Repo hygiene:** `.gitignore` now ignores `*.pt` / `*.onnx` (weights download into the repo root); benchmark weights I downloaded for testing were deleted (`yolo11n/s`, `yolo26m/x`); a temporary synthetic upload used to test the multipart path was removed from DB and disk.
- **New `scripts/run_local.sh`** (`sh -n` verified): creates `.venv` with `python3` if missing, installs backend requirements only when imports fail, copies `.env`, installs web deps if needed, writes `web/.env.local`, starts uvicorn + `next dev`, and kills the API on Ctrl-C.

---

## 5. Documentation brought up to date

- **README.md** — multi-scale feature bullet; first-run expectation of CPU runtime (≈1–2 min for short 1080p, ≈30 min for the 38 s 4K clip) and progress in the dashboard; `python3 -m venv` + note on pinning 3.12 (`uv venv --python 3.12 .venv`); validation section now uses `python3 -m pytest -q backend/tests`, `python3 scripts/check_project.py`, plus the frontend checks and a pointer to `docs/BUILD_STATUS.md`; repository structure mentions `run_local.sh`; new limitation bullet on extreme zoom-out frames reporting 0.
- **docs/AI_MODELS.md** — default `yolo26s.pt`, `imgsz` 1280, multi-scale pass description and its honest failure mode.
- **docs/ARCHITECTURE.md** — default model + multi-scale fallback described.
- **docs/DEPLOYMENT.md** — `python3 -m venv`, measured 4K CPU cost and how to trade it off (`PARKWISE_FRAME_STRIDE`, `PARKWISE_MULTISCALE`).
- **docs/BUILD_STATUS.md** — rewritten: what is now actually verified on a live machine vs. what still isn't (Docker, browser automation, GPU, full occupancy run).
- **`.env.example` / `.env`** — `yolo26s.pt`, `1280`, `PARKWISE_MULTISCALE=true`.

---

## 6. Verification performed

| Check | Result |
|---|---|
| `python3 -m pytest -q backend/tests` | 9 passed |
| `python3 scripts/check_project.py` | 11 app files parsed, core files present |
| `python3 -m compileall -q backend/app` | OK |
| `cd web && npx eslint .` | 0 errors, 2 documented warnings |
| `npx tsc --noEmit` | clean |
| `npm run build` | production build OK (static routes `/`, `/_not-found`) |
| `GET /api/health`, `/api/dashboard/summary`, `/api/config/public`, `/api/public-sources` | correct, honest empty-state before processing |
| `POST /api/public-sources/pexels-tom-fisk-3848792/fetch` | 201, 112 MB real clip (10 s) |
| `POST /api/videos/upload` (multipart) | 201, real metadata + preview; synthetic fixture cleaned up afterwards |
| `POST /api/videos/{id}/process` → completed | 379 samples, counts 0–223, mean conf 0.545 |
| `GET .../analytics`, `/preview`, `/annotated` | series present; annotated = `video/mp4`, 109 MB, 200 |
| Spaces `POST`/`GET`/`DELETE` | 201 / list / 204; DB left clean |
| `WS /api/ws/videos/{id}` | streaming progress frames received |
| Dashboard HTML (`curl localhost:3000`) | SSR contains “ParkWise / Parking overview / Video lab”, no error markers |

**Not verified here:** `docker compose up --build` (Docker CLI present but WSL integration disabled in this distro); automated browser click-through (bundled headless Chromium missing system libs such as `libnspr4`, no passwordless sudo); GPU inference; a full analysis run *with* calibrated polygons (API path tested, occupancy end-to-end not).

---

## 7. Current state / how to use it

```bash
# services already running from this session:
#   API  http://localhost:8000  (docs: /docs)   -> .venv/bin/python3 -m uvicorn app.main:app --app-dir backend ...
#   Web  http://localhost:3000                  -> cd web && npm run dev
# cold start later:
./scripts/run_local.sh          # python3, sets up venv/.env/node_modules if missing
```

Database currently holds two real completed jobs: the fetched Tom Fisk Pexels clip and the operator-uploaded `12600828_3840_2160_30fps.mp4`. Model weights cached at repo root: `yolo26s.pt` (default), `yolo26n.pt`. Session logs: `/tmp/opencode/parkwise-api.log`, `/tmp/opencode/parkwise-web.log`.

## 8. Files changed or added

```
backend/app/services/video_pipeline.py   multi-scale inference, ffmpeg resolution fallback
backend/app/config.py                    defaults: yolo26s.pt, 1280, multiscale=true
backend/app/api/routes.py                /api/config/public exposes multiscale
backend/requirements.txt                 + imageio-ffmpeg
web/app/page.tsx                         lint fixes, keyed per-video state, multiscale UI row
scripts/run_local.sh                     NEW: python3 launcher for API + dashboard
.env.example, .env                       updated defaults + PARKWISE_MULTISCALE
.gitignore                               + *.pt, *.onnx
README.md, docs/AI_MODELS.md, docs/ARCHITECTURE.md, docs/DEPLOYMENT.md, docs/BUILD_STATUS.md
web/.env.local                           created (NEXT_PUBLIC_API_BASE_URL)
opencode.md                              NEW: this summary
```

## 9. Sensible next steps (session 1 — items 1 and 2 done in session 2)

1. End-to-end occupancy run: draw bay polygons on a static-camera clip, re-analyze, confirm per-space free/occupied transitions (only the API path is proven so far). — *still open*
2. ~~Add a `DELETE /api/videos/{id}` endpoint~~ — **done in session 2** (API + dashboard button + tests).
3. `PARKWISE_MULTISCALE=false` or a larger `PARKWISE_FRAME_STRIDE` for CPU-bound deployments; GPU build per `docs/AI_MODELS.md`.
4. Re-validate `docker compose up --build` on a host with working Docker; install browser-system libs if automated UI QA is wanted.

---

# Session 2 — 2026-10-22 (same day)

Goal: *fix the issues found in the session-1 review, fix the `ModuleNotFoundError: No module named 'cv2'` crash, and add a light theme with a toggle.*

## 1. The `cv2` crash — root cause and fix

The traceback came from `~/.local/lib/python3.14/site-packages/uvicorn`, i.e. the bare `uvicorn` command
resolved to the user-level Python 3.14 install, **not** `.venv` (which contains uvicorn, cv2 and the whole
CV stack under Python 3.12). Typical causes: activating the venv in a shell where `uvicorn` had already been
resolved (bash caches command paths — `hash -r` clears it), or PATH order.

- `scripts/run_local.sh` now launches `.venv/bin/python3 -m uvicorn ...` explicitly (it can no longer pick a
  foreign interpreter) and honours `PARKWISE_API_HOST` / `PARKWISE_API_PORT` from `.env` when writing
  `web/.env.local` — those two settings were previously declared but unused.
- `backend/app/services/video_pipeline.py` raises a self-explaining `ModuleNotFoundError` if cv2 is missing,
  naming the venv command and the launcher instead of a bare `import cv2` traceback.
- README "Run without Docker" now uses `.venv/bin/python3 -m uvicorn ...` and documents the pitfall + `hash -r`.

## 2. Review issues fixed

| # | Issue | Fix |
|---|---|---|
| 1 | No way to delete an imported video (`data/` had grown to 353 MB) | `DELETE /api/videos/{video_id}` (`routes.py`): 409 while queued/processing, deletes the job (cascades spaces + detection samples), deletes `OccupancySample` rows explicitly (no ORM relationship), then unlinks original/preview/annotated/`*_annotated_opencv.*`. Dashboard jobs table gained a trash button with a confirm dialog. |
| 2 | `OccupancySample` rows written but never read | `GET /api/videos/{video_id}/occupancy` → `OccupancySeries` (`OccupancyPoint`: space_id, space_name, timestamp, state, confidence), joined to bay names. New Analytics panel "Bay occupancy history" shows per-bay sample count, share occupied, state changes and latest state. |
| 3 | Unreachable branch in `video_pipeline.py` (`previous_state` pre-seeded with every id) | Removed `previous_state` and the dead `elif`; behaviour unchanged (documented hysteresis: a known bay never flips to `unknown` mid-run, it resets when a job is re-queued). |
| 4 | `docker-compose.yml` ran `yolo26n.pt` @ 640 with no `PARKWISE_MULTISCALE` | Compose defaults aligned with `config.py` / `.env.example`: `yolo26s.pt`, `1280`, `PARKWISE_MULTISCALE=true`. |
| 5 | Dead/unused code | Dropped the throwaway `preview = ...uuid4()` line in `_make_job`; `SourceOut` is now used (`PublicSourceList` response model for `/api/public-sources`); `__import__("asyncio").sleep` → normal `import asyncio`; stray blank line after `@lru_cache` in `config.py`. |
| 6 | UI copy said "Default: YOLO26 nano" | Now "Default: YOLO26 small (yolo26s.pt)" with the 1280/multi-scale description. |
| 7 | CI ran pytest + `next build` only | Frontend job now also runs `npm run lint` and `npx tsc --noEmit`. |
| 8 | Stale files | Deleted `scripts/start_local.sh`, `scripts/start_windows.ps1` (undocumented duplicates of `docker compose up --build`) and the stray root `package-lock.json` (it made Next.js infer the wrong workspace root and warn on every build — warning is gone). |

## 3. Light theme + toggle

- `web/app/globals.css` (35 KB, minified, almost no CSS variables) was rewritten programmatically: **every
  colour literal became `--pw-cN`**, declared in `:root` with its original dark value and overridden in
  `:root[data-theme="light"]` with a curated counterpart (role-aware: backgrounds, text, borders, shadows;
  surface ramp keeps panels lighter than the page; accent fills under white labels are darkened instead of
  flipped; pure-white glyph labels on gradient tiles stay white; modal scrims stay dark). Semantic tokens
  (`--bg`, `--panel`, `--text`, accents…) got light values too, plus `--pw-chart-grid/line/accent` used by the
  SVG chart in `page.tsx` (hard-coded `#253043` / `#a78bfa` / `#8b5cf6` would have been unreadable on white).
- `layout.tsx` injects a pre-paint bootstrap script: reads `localStorage("parkwise-theme")`, falls back to
  `prefers-color-scheme`, sets `<html data-theme>` before first paint (no flash; `suppressHydrationWarning`).
- `page.tsx`: `useTheme()` via `useSyncExternalStore` + a Sun/Moon toggle button in the top bar
  (`.theme-toggle`, `aria-label` "Switch to dark/light theme").
- Palette validated programmatically (no browser is available here): 0 same-rule colour pairs under 3:1
  contrast in either theme; the only bright-on-bright pairs left are white text on the violet primary button
  and brand/avatar tiles, which are intended.

## 4. Verification (session 2)

| Check | Result |
|---|---|
| `python3 -m pytest -q backend/tests` | 16 passed (9 + 7 new deletion/occupancy tests) |
| `python3 scripts/check_project.py` | 11 files parsed, core files present |
| `python3 -m compileall -q backend/app` | OK |
| `cd web && npx eslint .` | 0 errors, 2 documented `<img>` warnings |
| `npx tsc --noEmit` | clean |
| `npm run build` | OK, no workspace-root warning anymore |
| Live API: health, config/public, public-sources | OK (public sources now schema-typed) |
| Live upload → space → `GET .../occupancy` → `DELETE .../videos/{id}` | 201 / 201 / 200 `{"items":[]}` / 204, then 404 on read and re-delete, zero leftover files, list count unchanged |
| Dashboard SSR (`localhost:3000`) | renders Overview/Video Lab, theme bootstrap script and the toggle button present; compiled CSS serves both palettes |

**Not verified here:** the light theme rendered in a real browser (headless Chromium still missing
`libnspr4`), a full analysis run *with* calibrated polygons, Docker.

## 5. State after session 2

```bash
# running now:
#   API  http://localhost:8000  -> .venv/bin/python3 -m uvicorn app.main:app --app-dir backend --host 0.0.0.0 --port 8000
#   Web  http://localhost:3000  -> cd web && npm run dev
# cold start: ./scripts/run_local.sh
```

Database still holds the two real completed jobs from session 1 (nothing was deleted). New/changed files:
`backend/app/api/routes.py` (delete + occupancy endpoints), `backend/app/schemas.py`
(`PublicSourceList`, `OccupancyPoint`, `OccupancySeries`), `backend/app/services/video_pipeline.py`,
`backend/tests/test_video_admin.py` (new), `docker-compose.yml`, `.github/workflows/ci.yml`,
`scripts/run_local.sh`, `web/app/globals.css` (variable-ised + light palette), `web/app/layout.tsx`,
`web/app/page.tsx` (toggle, delete, occupancy panel), `README.md`, `docs/API.md`, `docs/BUILD_STATUS.md`,
`.env.example`.

## in the next chat we did the following:
] Research: summarize the 9 reference sources (YOLO26/11, license, RT-DETR, DeepStream, MapLibre, OWASP, datasets)
[✓] Map current codebase (backend endpoints/models, frontend sections, gaps for live streaming, users, settings)
[✓] Produce architecture plan for 3-section restructure (Dashboard, Live View, Reports & Settings) + streaming design
[✓] Backend: settings/persistence endpoints (model config, integrations, users, billing/plan)
[✓] Backend: live stream sessions (RTSP/HTTP source → decode → YOLO+tracking → WebSocket annotated frames)
[✓] Backend: analytics endpoints for Power-BI-style dashboard (KPIs, breakdowns, activity)
[•] Backend smoke test on live server + update .env.example/docker-compose/CI
[ ] Frontend: split page.tsx into lib/components/sections scaffolding
[ ] Frontend: sidebar restructure to 3 sections (Dashboard, Live View, Reports & Settings)
[ ] Frontend: Dashboard section (KPI cards, bar/pie charts, reviewed-videos annotation access)
[ ] Frontend: Live View section (live feed + real-time annotations + bottom upload/lab)
[ ] Frontend: Reports & Settings section (model, integrations, users, billing, system)
[ ] Tests for new endpoints + lint/tsc/build verification + docs update (README/API/BUILD_STATUS/opencode)