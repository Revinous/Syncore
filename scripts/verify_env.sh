#!/usr/bin/env bash
set -euo pipefail

git --version
node --version
npm --version
if command -v python >/dev/null 2>&1; then
  python --version
elif command -v python3 >/dev/null 2>&1; then
  python3 --version
else
  echo "python is not installed"
  exit 1
fi
docker --version
docker compose version
