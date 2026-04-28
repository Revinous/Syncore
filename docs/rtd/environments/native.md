# Native Mode (SQLite)

## Purpose

Native mode runs Syncore without containers for local development.

## Required Settings

- `SYNCORE_RUNTIME_MODE=native`
- `SYNCORE_DB_BACKEND=sqlite`
- `SQLITE_DB_PATH=.syncore/syncore.db`
- `REDIS_REQUIRED=false`

## Setup Steps

1. `make install-local`
2. `make db-local-init`
3. `make dev-local`

## Validation

- `curl http://localhost:8000/health`
- `curl http://localhost:8000/health/services`
- open `http://localhost:3000`
