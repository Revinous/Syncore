# Docker Mode (Postgres + Redis)

Docker mode runs Syncore with a service topology closer to enterprise deployment. It keeps the same API and interface behavior as native mode, but uses containerized services and PostgreSQL-backed storage.

Use Docker mode when you need:

- Postgres behavior instead of SQLite
- Redis available as a real service
- a repeatable Compose stack
- closer parity with deployment architecture

## What Docker Mode Starts

`make bootstrap` uses `docker-compose.yml` to start:

- Next.js Web UI on `http://localhost:3000`
- FastAPI orchestrator on `http://localhost:8000`
- PostgreSQL on `localhost:5432`
- Redis on `localhost:6379`

## Prerequisites

Install:

- Docker
- Docker Compose plugin

Verify:

```bash
docker --version
docker compose version
```

## Environment

Create `.env`:

```bash
cp .env.example .env
```

Recommended Docker settings:

```env
SYNCORE_RUNTIME_MODE=docker
SYNCORE_DB_BACKEND=postgres
POSTGRES_DSN=postgresql://agentos:agentos@postgres:5432/agentos
REDIS_URL=redis://redis:6379/0
REDIS_REQUIRED=true
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ORCHESTRATOR_INTERNAL_URL=http://orchestrator:8000
```

The exact hostnames depend on whether the process runs inside Docker or from your host shell.

## Start

```bash
make bootstrap
```

`make bootstrap` delegates to `scripts/bootstrap.sh`, which builds/starts the stack and waits for health.

## Validate

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/health/services
```

Open:

```text
http://localhost:3000
```

## Logs

```bash
make logs
```

Use logs when:

- orchestrator health fails
- web cannot reach API
- Postgres or Redis is unhealthy

## Reset Docker State

```bash
docker compose down -v
make bootstrap
```

This removes volumes and discards Postgres data. Use it only when you intentionally want a clean database.

## CLI Against Docker Mode

The CLI can talk to Docker mode as long as the orchestrator is exposed:

```bash
export SYNCORE_API_URL=http://localhost:8000
syncore status
syncore workspace list
```

The CLI should still write through the API, not directly to Postgres.

## Common Docker Problems

Postgres connection fails:

- check `docker compose ps`
- check `POSTGRES_DSN`
- check orchestrator logs with `make logs`

Redis degraded:

- check `REDIS_REQUIRED=true`
- check `REDIS_URL`
- confirm redis container is running

Web UI cannot reach API:

- confirm `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`
- confirm browser can reach `http://localhost:8000/health`

Data differs from native mode:

- expected if native SQLite and Docker Postgres were both used
- verify active backend with `/diagnostics/config`
