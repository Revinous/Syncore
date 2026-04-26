#!/usr/bin/env bash
set -euo pipefail

cp -n .env.example .env || true
set -a
source .env
set +a

if [[ ! -x ".venv/bin/python" ]]; then
  echo "[dev-local] missing .venv. Run: make install-local"
  exit 1
fi

export SYNCORE_RUNTIME_MODE="${SYNCORE_RUNTIME_MODE:-native}"
export SYNCORE_DB_BACKEND="${SYNCORE_DB_BACKEND:-sqlite}"
export SQLITE_DB_PATH="${SQLITE_DB_PATH:-.syncore/syncore.db}"
export REDIS_REQUIRED="${REDIS_REQUIRED:-false}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-http://localhost:8000}"
export ORCHESTRATOR_INTERNAL_URL="${ORCHESTRATOR_INTERNAL_URL:-http://localhost:8000}"

ORCHESTRATOR_PORT="${ORCHESTRATOR_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"

if [[ "${SYNCORE_DB_BACKEND}" == "sqlite" && ! -f "${SQLITE_DB_PATH}" ]]; then
  bash scripts/init_local_sqlite.sh
fi

cleanup() {
  if [[ -n "${ORCH_PID:-}" ]]; then
    pkill -TERM -P "${ORCH_PID}" 2>/dev/null || true
    kill "${ORCH_PID}" 2>/dev/null || true
  fi
  if [[ -n "${WEB_PID:-}" ]]; then
    pkill -TERM -P "${WEB_PID}" 2>/dev/null || true
    kill "${WEB_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

PYTHONPATH=services/orchestrator:. \
  .venv/bin/python -m uvicorn app.main:app \
  --app-dir services/orchestrator \
  --host 0.0.0.0 \
  --port "${ORCHESTRATOR_PORT}" \
  --reload &
ORCH_PID=$!

(
  cd apps/web
  PORT="${WEB_PORT}" ./node_modules/.bin/next dev --port "${WEB_PORT}"
) &
WEB_PID=$!

echo "[dev-local] orchestrator pid=${ORCH_PID} port=${ORCHESTRATOR_PORT}"
echo "[dev-local] web pid=${WEB_PID} port=${WEB_PORT}"
echo "[dev-local] open http://localhost:${WEB_PORT} and http://localhost:${ORCHESTRATOR_PORT}/health"

wait -n "${ORCH_PID}" "${WEB_PID}"
