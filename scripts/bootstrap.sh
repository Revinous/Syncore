#!/usr/bin/env bash
set -euo pipefail

cp -n .env.example .env || true

docker compose up -d --build postgres redis

echo "Waiting for PostgreSQL to become available..."
until docker exec agent-postgres pg_isready -U agentos >/dev/null 2>&1; do
  sleep 2
done

echo "PostgreSQL is ready."
echo "Applying database initialization/migration script..."
docker exec -i agent-postgres psql -U agentos -d agentos < scripts/init_db.sql
echo "Stamping and applying Alembic migrations..."
docker compose run --rm \
  -e SYNCORE_DB_BACKEND=postgres \
  -e POSTGRES_DSN="postgresql://agentos:agentos@postgres:5432/agentos" \
  orchestrator bash -lc "cd /workspace/services/orchestrator && alembic -c alembic.ini stamp head && alembic -c alembic.ini upgrade head"

docker compose up -d --build orchestrator web

echo "Waiting for orchestrator health endpoint..."
until curl -fsS "http://localhost:8000/health" >/dev/null 2>&1; do
  sleep 2
done

echo "Orchestrator is healthy."

docker compose ps
