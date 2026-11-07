# Local and Production Deployment Guide

## Docker Compose (Production & Pilot)

The recommended deployment method runs a unified reverse-proxy stack using Caddy, Next.js, and FastAPI.

```bash
cp .env.example .env
docker compose up -d --build
```

### Services Deployed

1. **`proxy` (Caddy)**: Listens on ports `80` and `443`. Proxies `/api/*` and `/api/ws/*` to the FastAPI backend and all other routes to Next.js. Provides automatic HTTPS, Gzip/Zstandard compression, and unified same-origin routing (no CORS configuration needed).
2. **`web` (Next.js 16)**: Standalone SSR/Static frontend container running on internal port `3000`.
3. **`api` (FastAPI)**: Computer vision processing backend container running on internal port `8000`.

### Bootstrapping the First Administrator

When `PARKWISE_AUTH_REQUIRED=true` (enabled by default in Docker):

```bash
docker compose exec api python scripts/bootstrap_admin.py
```

The script prints a cryptographically secure random API key. You can authenticate either:
- In the Web Dashboard: Enter the key under **Settings > Users & Access**.
- Via HTTP header: `X-API-Key: <your-key>`

---

## Bare-Metal Development

### 1. Backend Service

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements-dev.txt
uvicorn app.main:app --app-dir backend --port 8000 --reload
```

### 2. Frontend Development

```bash
cd web
npm install
npm run dev
```

---

## Vercel Deployment (Frontend)

The Next.js 16 frontend is pre-configured for one-click deployment on [Vercel](https://vercel.com). Because the backend runs long-running computer vision pipelines, OpenCV/PyTorch models, and persistent WebSocket streams, the backend is hosted on a container/cloud platform (Railway, Render, Fly.io, AWS, or VPS) while the frontend runs globally on Vercel.

### 1. Import Project to Vercel

1. In the Vercel dashboard, click **Add New... > Project** and import the `PARKWISE_AI` repository.
2. Under **Root Directory**, click **Edit** and select `web` (or leave default if using the root `vercel.json`).
3. Framework Preset will auto-detect as **Next.js**.

### 2. Configure Environment Variables in Vercel

In Vercel **Project Settings > Environment Variables**, define:

| Variable | Value | Description |
| :--- | :--- | :--- |
| `NEXT_PUBLIC_API_BASE_URL` | `https://api.yourdomain.com` | Public URL of your deployed FastAPI backend (no trailing slash). |
| `NEXT_PUBLIC_EXTRA_CSP_ORIGINS` | *(Optional)* | Additional CDN or tile origins to whitelist in CSP. |

> **Note**: `NEXT_PUBLIC_API_BASE_URL` is baked into the frontend bundle at build time, so configure it before triggering the deployment build. The Next.js Content Security Policy (CSP) will automatically allow your API origin for REST calls, preview images, and video streaming.

### 3. Configure Backend for Vercel

On your backend environment (Railway, Render, Docker, or VPS):

1. **Allow Vercel CORS Origins**:
   ```bash
   # In backend .env:
   # For production domain:
   PARKWISE_ALLOWED_ORIGINS=https://your-parkwise-app.vercel.app,https://dashboard.yourdomain.com

   # For Vercel preview branch deployments:
   PARKWISE_ALLOWED_ORIGIN_REGEX=^https://[a-zA-Z0-9-]+\.vercel\.app$
   ```
2. **Ensure Production Security**:
   ```bash
   PARKWISE_ENV=production
   PARKWISE_AUTH_REQUIRED=true
   PARKWISE_MEDIA_SIGNING_SECRET=<generate-a-strong-secret-key>
   ```
3. **Bootstrap Admin Key**:
   Run `.venv/bin/python scripts/bootstrap_admin.py --username admin --display-name "Administrator"` on the backend to generate the administrator key.

---

## Database Connection Pooling & PostgreSQL

For production multi-camera deployments, switch from SQLite to PostgreSQL:

```bash
# In .env
PARKWISE_DATABASE_URL=postgresql+psycopg://parkwise:password@postgres-host:5432/parkwise
PARKWISE_DB_POOL_SIZE=10
PARKWISE_DB_MAX_OVERFLOW=20
PARKWISE_DB_POOL_RECYCLE=1800
PARKWISE_DB_POOL_TIMEOUT=30
```

---

## Hardware Acceleration (NVIDIA CUDA / Jetson)

To utilize an NVIDIA GPU:
1. Ensure the NVIDIA Container Toolkit is installed on the host.
2. In `docker-compose.yml`, assign the `gpu` device reservation.
3. Configure `PARKWISE_DEVICE=0` (or `cuda:0`).
4. To run serverless or edge deployments without PyTorch GPU dependencies, export weights to ONNX:
   ```bash
   python scripts/export_model_onnx.py yolo26s.pt
   ```
