# Local and production deployment

## Docker Compose (recommended for a pilot)

```bash
cp .env.example .env
docker compose up --build
```

The API is exposed on port 8000 and web UI on port 3000. Docker creates a named volume `parkwise_data` so the database, videos, previews and annotated files persist across container restarts. Confirm the healthcheck at `GET /api/health` and the generated schema at `/docs`.

The first build downloads Python/Node packages; the first inference may also download YOLO weights. PyTorch and model weights are large, so plan sufficient disk and RAM. Processing long 4K video on CPU can be slow. Start with a short clip and adjust `PARKWISE_FRAME_STRIDE` / `PARKWISE_IMAGE_SIZE` based on a measured quality-speed trade-off. With `PARKWISE_MULTISCALE=true` a 4K clip can spend several seconds per sampled frame on the extra sharp passes; disable it or raise the frame stride when CPU time matters more than small-vehicle recall.

## Native development

Terminal 1:

```bash
python3 -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .venv\\Scripts\\Activate.ps1
pip install -r backend/requirements.txt
uvicorn app.main:app --app-dir backend --reload --port 8000
```

Terminal 2:

```bash
cd web
cp .env.example .env.local
npm install
npm run dev
```

## PostgreSQL and object storage

For a multi-user installation, provision PostgreSQL, install a matching driver such as `psycopg[binary]`, set `PARKWISE_DATABASE_URL`, and add schema migrations (Alembic). Replace filesystem media paths with object storage keys and signed/authorized media routes; do not expose arbitrary raw video paths.

## Reverse proxy

Terminate HTTPS at a trusted proxy, configure `PARKWISE_ALLOWED_ORIGINS` to exact browser origins, limit request body sizes at the proxy, rate-limit upload/fetch routes, and keep `/docs` private if appropriate. Do not publish the pilot without authentication/RBAC and retention policy. WebSocket upgrades must be proxied for `/api/ws/videos/*`.

## NVIDIA GPU / Jetson

The current Docker image is generic and will typically use CPU inference unless the container has the compatible CUDA/PyTorch runtime and a device is selected. Install a PyTorch package that matches the host driver, test the actual model on target hardware, and then set `PARKWISE_DEVICE=0`. For Jetson/production edge, evaluate NVIDIA DeepStream/TensorRT and validate exported model outputs against PyTorch before rollout.
