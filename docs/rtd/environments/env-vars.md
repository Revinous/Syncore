# Environment Variables

## Core

- `SYNCORE_RUNTIME_MODE`: `native` or `docker`
- `SYNCORE_DB_BACKEND`: `sqlite` or `postgres`
- `SYNCORE_API_URL`: CLI/TUI API base (default `http://localhost:8000`)
- `NEXT_PUBLIC_API_BASE_URL`: Web UI API base

## Native DB

- `SQLITE_DB_PATH`: SQLite file path

## Docker/Enterprise DB

- `POSTGRES_DSN`: Postgres DSN
- `REDIS_URL`: Redis URL
- `REDIS_REQUIRED`: `true|false`

## Optional Feature Flags

- `AUTONOMY_ENABLED`
- `CONTEXT_LAYERING_ENABLED`
- `CONTEXT_LAYERING_DUAL_MODE`
