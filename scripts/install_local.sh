#!/usr/bin/env bash
set -euo pipefail

cp -n .env.example .env || true

if ! command -v uv >/dev/null 2>&1; then
  echo "[install-local] missing required tool: uv"
  echo "Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  exit 1
fi

uv venv .venv
uv pip install --python .venv/bin/python -r services/orchestrator/requirements.txt
uv pip install --python .venv/bin/python -r services/orchestrator/requirements-dev.txt

npm --prefix apps/web ci

echo "[install-local] dependencies installed via uv-managed .venv"
