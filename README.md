# ParkWise

[![CI](https://github.com/Jack-ki1/PARK_WISE_AI/actions/workflows/ci.yml/badge.svg)](https://github.com/Jack-ki1/PARK_WISE_AI/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![WCAG 2.1 AA](https://img.shields.io/badge/WCAG%202.1-AA%20Compliant-green.svg)](scripts/check_contrast.py)
[![Accuracy: 96.2% F1](https://img.shields.io/badge/Holdout%20F1-96.2%25-success.svg)](scripts/evaluate_occupancy.py)

**Measured per-bay parking occupancy and vehicle tracking from real camera footage — not guesswork.**

![ParkWise Operations Dashboard](web/public/showcase/dashboard-light.png)

---

## Quick Start

### 1. Docker Compose (Recommended)

Prerequisites: [Docker Engine](https://docs.docker.com/engine/install/) & Docker Compose.

```bash
# Launch unified stack (Caddy reverse proxy on :80/:443, Next.js UI, FastAPI API)
docker compose up -d

# Mint initial administrator API key
docker compose exec api python scripts/bootstrap_admin.py

# Access the operations dashboard
open http://localhost
```

*Note: In Docker, Caddy proxies all API requests (`/api/*`) and WebSocket streams (`/api/ws/*`) to the backend, serving everything from the same origin (`http://localhost`) with zero CORS complexity.*

### 2. Bare-Metal Local Development

Prerequisites: Python 3.12+ and Node.js 20+.

```bash
# Terminal 1 — Backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --port 8000 --reload

# Terminal 2 — Frontend
cd web
npm install
npm run dev
```

---

## Quality & Accuracy Gates

ParkWise enforces empirical quality and accessibility verification directly in CI:

```bash
# 1. Run full backend test suite (154 tests)
pytest backend/tests

# 2. Verify WCAG 2.1 AA color contrast compliance (Light & Dark tokens)
python scripts/check_contrast.py

# 3. Run empirical accuracy evaluation benchmark (Precision, Recall, False-Free rate)
python scripts/evaluate_occupancy.py

# 4. Frontend lint & static build verification
cd web && npm run lint && npm run build
```

---

## What It Does

- **Real Computer Vision Inference**: Runs YOLO (YOLO26 / ONNX / RT-DETR) with ByteTrack persistent vehicle tracking over RTSP/HLS streams and uploaded video footage.
- **Per-Bay Occupancy State Machine**: Computes intersection-over-bay coverage with time-based hysteresis, suppressing false transitions from brief occlusions or passing cars.
- **Empirical Quality Gating**: Automatically detects glare, dark frames, or camera freezing, transitioning bays to `unknown` rather than reporting false capacity.
- **100% On-Prem & Private**: Video frames remain in volatile host memory during inference. Zero video data leaves your infrastructure perimeter.
- **Role-Based Security**: Hardened API with SHA-256 key hashing, HMAC-signed media URLs, single-use WebSocket tickets, and strict CSP headers.

---

## Measured Accuracy

Empirically validated across 1,200 holdout observations with varying weather and lighting conditions:

| Operational Condition | Samples | Precision | Recall | False-Free Rate* | Unknown Rate |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Daylight Clear** | 500 | 96.5% | 99.6% | **0.4%** | 2.4% |
| **Night / Low-Light** | 350 | 92.9% | 99.4% | **0.6%** | 5.4% |
| **Rain / Glare Surface** | 350 | 88.6% | 99.4% | **0.6%** | 7.1% |
| **Overall Weighted** | **1,200** | **93.1%** | **99.5%** | **0.5%** | **4.7%** |

*\*False-free rate measures an occupied bay erroneously marked free. Drivers circling full lots is the most costly parking failure; ParkWise prioritizes marking uncertain bays as `unknown` over false-free.*

Run the evaluation harness locally:
```bash
python scripts/evaluate_occupancy.py
```

---

## Architecture

```
 Browser (Next.js 16 / React 19 / TanStack Query)
    │  REST (X-API-Key / Session Storage) & WebSockets
    ▼
 Caddy Reverse Proxy (Port 80/443, SSL/TLS, Gzip/Zstd)
    ├── /api/ws/*  ──────►  FastAPI WebSocket tickets & frame binary stream
    ├── /api/*     ──────►  FastAPI REST API (Request context, Redis ratelimit)
    └── /*         ──────►  Next.js Standalone UI
    ▼
 Processing Engine
    ├── Pluggable Detector Protocol (Ultralytics / ONNX Runtime / OpenCV DNN)
    ├── BayStateMachine (IoU overlap + dwell hysteresis + quality gates)
    └── Storage & Database (SQLite dev default / Postgres 17 pool + PostGIS)
```

---

## Documentation

- [System Architecture](docs/ARCHITECTURE.md)
- [REST & WebSocket API Specification](docs/API.md)
- [Detection Models & Licensing Notice](docs/AI_MODELS.md)
- [Production Deployment & Hardening](docs/DEPLOYMENT.md)
- [Security Model & Threat Profile](docs/SECURITY.md)
- [Changelog](CHANGELOG.md)

---

## License

ParkWise core software is licensed under the [MIT License](LICENSE). 

*Model Backends Note*: Detection runs through a pluggable `Detector` interface. While permissive ONNX/Mock backends run under Apache-2.0/MIT, the optional Ultralytics YOLO engine is subject to AGPL-3.0 or Ultralytics Enterprise licensing. See [AI_MODELS.md](docs/AI_MODELS.md) for details.
