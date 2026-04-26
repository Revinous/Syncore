#!/usr/bin/env bash
set -euo pipefail

cp -n .env.example .env || true

python3 -m venv .venv
source .venv/bin/activate

python -m pip install --upgrade pip
python -m pip install -r services/orchestrator/requirements.txt
python -m pip install -r services/orchestrator/requirements-dev.txt

npm --prefix apps/web ci

echo "[install-local] dependencies installed"
