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
AUTH_REQUIRED=$(sed -n 's/^PARKWISE_AUTH_REQUIRED=//p' .env | tail -n 1)
: "${API_HOST:=127.0.0.1}"
: "${API_PORT:=8000}"
: "${AUTH_REQUIRED:=true}"

if [ ! -d web/node_modules ]; then
  echo "Installing web dependencies..."
  (cd web && npm install)
fi
# NEXT_PUBLIC_* values are inlined into the browser bundle at compile time, so
# the dev server must be (re)started whenever this URL changes — it is not read
# live from .env.local. A 0.0.0.0 bind is still reached from the browser as
# localhost, so rewrite it here instead of advertising an unusable URL.
API_BROWSER_HOST=$API_HOST
case "$API_HOST" in
  0.0.0.0|"::"|"[::]") API_BROWSER_HOST=localhost ;;
esac
API_BASE="http://${API_BROWSER_HOST}:${API_PORT}"
if [ "$(cat web/.env.local 2>/dev/null)" != "NEXT_PUBLIC_API_BASE_URL=${API_BASE}" ]; then
  printf 'NEXT_PUBLIC_API_BASE_URL=%s\n' "$API_BASE" > web/.env.local
  echo "Set NEXT_PUBLIC_API_BASE_URL=${API_BASE} in web/.env.local"
fi

# Always launch through the venv interpreter: a system `uvicorn` would run a
# different Python and fail with "No module named 'cv2'". Host/port come from
# .env, which is where the API itself reads them — pass them explicitly so a
# non-default port in .env is actually honoured.
.venv/bin/python3 -m uvicorn app.main:app --app-dir backend --host "$API_HOST" --port "$API_PORT" &
API_PID=$!

# Do not print "ready" until health actually answers: opening the dashboard
# before the API is listening shows a false "API offline" banner.
echo "Waiting for the API on ${API_BASE} ..."
for _ in $(seq 1 60); do
  curl -fsS -m 2 "${API_BASE}/api/health" >/dev/null 2>&1 && break
  kill -0 "$API_PID" 2>/dev/null || break
  sleep 1
done
if curl -fsS -m 2 "${API_BASE}/api/health" >/dev/null 2>&1; then
  echo "API  ${API_BASE}  (docs: /docs)"
  # With auth on, the dashboard stays empty until a key exists — say so up front
  # instead of letting the user puzzle over 401 banners.
  case "$AUTH_REQUIRED" in
    true|True|TRUE|1)
      if ! curl -fsS -m 2 "${API_BASE}/api/dashboard/summary" >/dev/null 2>&1; then
        echo "Auth is enabled: paste an API key in the dashboard (Reports & Settings ->"
        echo "API key access). First key? Create one with:"
        echo "  .venv/bin/python3 scripts/bootstrap_admin.py --username admin --display-name \"Admin\""
      fi
      ;;
  esac
else
  echo "API did not become healthy at ${API_BASE}/api/health — see the log above."
fi
cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "Web  http://localhost:3000"
cd web && npm run dev
