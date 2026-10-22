#!/usr/bin/env sh
# Start the FastAPI backend and the Next.js dashboard locally with python3 (no Docker).
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cd "$ROOT"

if [ ! -d .venv ]; then
  echo "Creating .venv with python3..."
  python3 -m venv .venv
fi
# shellcheck source=/dev/null
. .venv/bin/activate
if ! python3 -c "import fastapi, ultralytics, cv2" >/dev/null 2>&1; then
  echo "Installing backend requirements..."
  python3 -m pip install -q -r backend/requirements.txt
fi

[ -f .env ] || cp .env.example .env

# PARKWISE_API_HOST / PARKWISE_API_PORT come from .env (defaults match config.py).
# Reading them here is what makes those settings meaningful outside Docker.
API_HOST=$(sed -n 's/^PARKWISE_API_HOST=//p' .env | tail -n 1)
API_PORT=$(sed -n 's/^PARKWISE_API_PORT=//p' .env | tail -n 1)
: "${API_HOST:=0.0.0.0}"
: "${API_PORT:=8000}"

if [ ! -d web/node_modules ]; then
  echo "Installing web dependencies..."
  (cd web && npm install)
fi
if ! grep -q "http://localhost:${API_PORT}" web/.env.local 2>/dev/null; then
  printf 'NEXT_PUBLIC_API_BASE_URL=http://localhost:%s\n' "$API_PORT" > web/.env.local
fi

# Always launch through the venv interpreter: a system `uvicorn` would run a
# different Python and fail with "No module named 'cv2'".
.venv/bin/python3 -m uvicorn app.main:app --app-dir backend --host "$API_HOST" --port "$API_PORT" &
API_PID=$!
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "API  http://localhost:${API_PORT}  (docs: /docs)"
echo "Web  http://localhost:3000"
cd web && npm run dev
