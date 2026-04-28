# Docker Mode (Postgres + Redis)

## Purpose

Docker mode provides a production-like local topology.

## Required Settings

- `SYNCORE_RUNTIME_MODE=docker`
- `SYNCORE_DB_BACKEND=postgres`
- `POSTGRES_DSN=postgresql://...`
- `REDIS_REQUIRED=true`

## Setup Steps

1. `cp .env.example .env`
2. `make bootstrap`

## Validation

- `docker compose ps`
- `curl http://localhost:8000/health`
- `curl http://localhost:8000/health/services`
