# Native Mode (SQLite)

Native mode is the solo developer path. It runs the FastAPI orchestrator and Next.js Web UI directly on your machine and stores durable workflow state in SQLite by default.

Use native mode when you are:

- developing Syncore itself
- testing CLI/TUI flows quickly
- attaching Syncore to a local repo
- running without Docker, Postgres, or Redis

## What Native Mode Starts

`make dev-local` starts:

- FastAPI orchestrator on `http://localhost:8000`
- Next.js Web UI on `http://localhost:3000`
- SQLite database at `SQLITE_DB_PATH`

Redis is optional in this mode. The expected local setting is `REDIS_REQUIRED=false`.

## Prerequisites

Install:

- Python 3.11+
- Node 20+
- npm
- uv

Verify:

```bash
python3 --version
node --version
npm --version
uv --version
```

## Environment

Create `.env`:

```bash
cp .env.example .env
```

Recommended native settings:

```env
SYNCORE_RUNTIME_MODE=native
SYNCORE_DB_BACKEND=sqlite
SQLITE_DB_PATH=.syncore/syncore.db
REDIS_REQUIRED=false
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
ORCHESTRATOR_INTERNAL_URL=http://localhost:8000
```

If these values are omitted, native helper scripts set safe defaults for local startup.

## Install Dependencies

```bash
make install-local
```

What this does:

- creates `.venv` with `uv`
- installs orchestrator runtime dependencies
- installs orchestrator dev/test dependencies
- runs `npm ci` in `apps/web`
- installs a global `syncore` launcher under `~/.local/bin`

If `syncore` is not found after install, add this to your shell:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

## Initialize SQLite

```bash
make db-local-init
```

Expected result:

```text
[db-local-init] initialized sqlite database at .syncore/syncore.db
```

The script creates `.syncore/` if needed and applies `scripts/init_sqlite.sql`.

## Start Services

```bash
make dev-local
```

Expected output includes:

- orchestrator PID and port
- web PID and port
- health URL

Keep this terminal running. Open a second terminal for CLI commands.

## Validate

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/services
syncore status
```

Open:

```text
http://localhost:3000
```

## First Workspace

```bash
syncore workspace add . --name syncore
syncore workspace scan syncore
syncore open syncore
```

`syncore open` starts a scoped TUI session for the workspace.

## Auto-Start Behavior

`syncore tui` and `syncore open <workspace>` can auto-start the orchestrator when:

- API URL is local (`localhost` or `127.0.0.1`)
- `SYNCORE_RUNTIME_MODE=native`
- `SYNCORE_DB_BACKEND=sqlite`
- `.venv/bin/python` exists

Auto-start initializes SQLite if needed and writes logs to:

```text
.syncore/orchestrator-cli.log
```

## Native Test Path

```bash
make local-test
```

This runs memory and orchestrator tests against SQLite settings.

## Common Native Problems

`syncore` command not found:

- confirm `~/.local/bin` is in `PATH`
- rerun `make install-local`

API connection refused:

- run `make dev-local`
- check `.syncore/orchestrator-cli.log` if auto-start was used

Missing task/workspace data:

- confirm you are still using SQLite mode
- check `curl http://localhost:8000/diagnostics/config`

Stale process on port `8000`:

- stop the old process or set `ORCHESTRATOR_PORT` before `make dev-local`
