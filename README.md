# Syncore Local MVP Operator Guide

Syncore is a local-first orchestration platform prototype where specialized agent roles hand off work through structured baton packets, persist durable state, and generate analyst digests from real project events.

This guide is intentionally focused on **local MVP validation only**. It does not add AWS, staging hardening, or production scope.

For full beginner-to-advanced usage, see [docs/USER_GUIDE.md](docs/USER_GUIDE.md).

This repository is optimized for one believable local workflow:

1. Create a task.
2. Start agent runs.
3. Handoff baton packets.
4. Persist project events.
5. Route next action.
6. Generate analyst digest.
7. Inspect all state from API and developer console.

## Architecture At A Glance

```text
┌───────────────────────┐
│      Next.js UI       │  http://localhost:3000
│  (local console page) │
└───────────┬───────────┘
            │ HTTP
            ▼
┌───────────────────────────────────────────────────────┐
│            FastAPI Orchestrator (localhost:8000)     │
│ Routes: tasks, runs, baton, events, routing, digest  │
│ Services: task/run/baton/event/routing/analyst       │
└───────────┬───────────────────────────────┬───────────┘
            │                               │
            │                               │
            ▼                               ▼
┌───────────────────────┐         ┌───────────────────────┐
│ PostgreSQL or SQLite  │         │ Redis (optional in     │
│ durable workflow data │         │ native mode)           │
│ tasks/runs/events/... │         │ coordination/cache     │
└───────────────────────┘         └───────────────────────┘
```

## Repository Layout

- `apps/web` – Next.js local console for workflow visibility.
- `services/orchestrator` – FastAPI API + orchestration service layer.
- `services/memory` – PostgreSQL + SQLite store implementations behind a shared factory.
- `services/router` – deterministic routing policy engine.
- `services/analyst` – digest generation from stored events.
- `packages/contracts` – shared typed contracts (Python + TypeScript).
- `scripts` – bootstrap, DB init, local demo flow.
- `infra/docker` – local Dockerfiles.
- `infra/terraform` – Phase 4 AWS placeholder infrastructure.
- `docs` – validation reports, runbooks, project docs.

## Prerequisites

Install and verify:

- `git`
- `node` (20+)
- `npm`
- `python3` (3.10+; 3.11 preferred)
- `uv` (for native Python virtualenv + dependency install)
- `docker` + `docker compose` (required for Docker lane only)

Verify quickly:

```bash
git --version
node --version
npm --version
python3 --version
docker --version
docker compose version
```

## Environment Variables

Copy and edit as needed:

```bash
cp .env.example .env
```

Key variables:

- `ORCHESTRATOR_BASE_URL` – local API base (default `http://localhost:8000`)
- `NEXT_PUBLIC_API_BASE_URL` – browser-side web app API base
- `ORCHESTRATOR_INTERNAL_URL` – server-side web app API base
- `SYNCORE_RUNTIME_MODE` – `native` or `docker`
- `SYNCORE_DB_BACKEND` – `sqlite` or `postgres`
- `SQLITE_DB_PATH` – sqlite database location for native mode
- `POSTGRES_DSN` – PostgreSQL DSN for Docker/enterprise mode
- `REDIS_URL` – redis connection string
- `REDIS_REQUIRED` – set `false` for native mode without redis
- `AUTONOMY_ENABLED` – set `true` to auto-process new tasks
- `AUTONOMY_POLL_INTERVAL_SECONDS` – background loop interval
- `AUTONOMY_DEFAULT_MODEL` – fallback model when preferences are absent
- `AUTONOMY_MAX_RETRIES` – max retries per autonomy stage before blocking
- `AUTONOMY_RETRY_BASE_SECONDS` – exponential backoff base for retries
- `AUTONOMY_MAX_CYCLES` – max replan cycles before blocking
- `AUTONOMY_MAX_TOTAL_STEPS` – hard cap on total autonomy stage attempts
- `AUTONOMY_REVIEW_PASS_KEYWORD` – review pass token required by gate
- `AUTONOMY_PLAN_MIN_CHARS` / `AUTONOMY_EXECUTE_MIN_CHARS` / `AUTONOMY_REVIEW_MIN_CHARS` – stage output quality gates
- `CONTEXT_LAYERING_ENABLED` – enable L0/L1/L2 context layering during optimization
- `CONTEXT_LAYERING_DUAL_MODE` – run legacy+layered comparison and attach token deltas for rollout analysis
- `CONTEXT_LAYERING_FALLBACK_THRESHOLD_PCT` – auto-fallback guardrail threshold when layered mode underperforms
- `CONTEXT_LAYERING_FALLBACK_MIN_SAMPLES` – minimum dual-mode samples before fallback policy activates
- `API_AUTH_ENABLED` / `API_AUTH_TOKEN` – optional API key protection (`x-api-key`)
- `RATE_LIMIT_ENABLED` / `RATE_LIMIT_WINDOW_SECONDS` / `RATE_LIMIT_MAX_REQUESTS` – optional request throttling
- Provider API keys are intentionally omitted from `.env.example`; add any secrets only in your local `.env`.

## Startup Lanes

### Enterprise / Docker Mode

Uses Docker Compose with PostgreSQL + Redis.

```bash
cp .env.example .env
make bootstrap
```

### Solo Developer / Native Mode

Runs FastAPI + Next.js directly on host, defaulting to SQLite.

```bash
cp .env.example .env
make bootstrap-local
make dev-local
```

Native mode initializes SQLite at `.syncore/syncore.db` and does not require Redis by default.
For autonomous task execution from raw task ideas, set `AUTONOMY_ENABLED=true`.

## Interfaces

Syncore has two first-class control surfaces that both use the FastAPI orchestrator API as source of truth.

1. Web UI
   - Browser-based enterprise control panel for dashboards, workspace management, task/run visibility, and diagnostics.
   - Start in native mode:
     - `make dev-local`
     - open `http://localhost:3000`
   - Start in Docker mode:
     - `make bootstrap`
     - open `http://localhost:3000`

2. CLI / TUI
   - Terminal-first local control surface for fast workflows and interactive monitoring.
   - Install:
     - `make install-cli`
  - Common commands:
    - `syncore status`
    - `syncore dashboard`
    - `syncore metrics context`
    - `syncore auth openai login`
    - `syncore auth openai models`
    - `syncore workspace list`
    - `syncore task list`
    - `syncore open my-app`
    - `syncore tui`

Environment variables used by interfaces:
- `SYNCORE_API_URL=http://localhost:8000`
- `NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`

OpenAI model access in CLI/TUI:
- Sign in locally with API key:
  - `syncore auth openai login`
- Inspect available models for your account:
  - `syncore auth openai models`
- In TUI:
  - press `i` to connect OpenAI
  - press `m` to refresh model list
  - press `n` to create a task and pick a preferred model

Examples:
- `syncore auth openai login`
- `syncore auth openai models`
- `syncore workspace add ./my-app --name my-app`
- `syncore workspace scan my-app`
- `syncore task create \"Analyze the auth flow\" --workspace my-app`
- `syncore task switch-model TASK_ID --provider openai --model gpt-5.4`
- `syncore run start TASK_ID --agent-role backend`
- `syncore run result RUN_ID`
- `syncore providers`
- `syncore open my-app`
- `syncore my-app` (shortcut for `syncore open my-app`)
- `syncore tui`

For both lanes, verify:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/services
open http://localhost:3000  # or paste in browser
```

## Local Ports

- Web: `3000`
- Orchestrator API: `8000`
- PostgreSQL: `5432`
- Redis: `6379`

## Common Commands

```bash
make bootstrap      # build/start stack and wait for health
make install-local  # create .venv + install Python and Node dependencies
make db-local-init  # initialize sqlite schema at SQLITE_DB_PATH
make dev-local      # run orchestrator + web without Docker
make bootstrap-local # install-local + db-local-init
make local-test     # run backend tests with sqlite backend env
make db-migrate     # apply Alembic migrations (native/docker based on env)
make up             # docker compose up -d --build
make down           # docker compose down
make logs           # tail compose logs
make demo-local     # run canonical local orchestration flow
make test           # backend + frontend tests
make check          # lint + tests + typecheck + build
```

Global CLI after `make install-local`:

```bash
syncore workspace                # start local workspace services (web + api)
syncore workspace add . --name Syncore
syncore workspace list
syncore workspace scan Syncore
syncore workspace files Syncore
syncore task create Syncore "Implement workspace scan route tests"
```

## API Endpoints (Local MVP)

- `GET /health`
- `GET /health/services`
- `GET /metrics`
- `GET /metrics/slo`
- `GET /metrics/context-efficiency`
  - includes `layering_comparison` when dual mode is active
- `GET /dashboard/summary`
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}`
- `POST /tasks/{task_id}/model-switch`
- `POST /agent-runs`
- `GET /agent-runs`
- `GET /agent-runs/{run_id}`
- `GET /agent-runs/{run_id}/result`
- `PATCH /agent-runs/{run_id}`
- `POST /baton-packets`
- `GET /baton-packets`
- `GET /baton-packets/{task_id}`
- `GET /baton-packets/by-id/{packet_id}`
- `POST /project-events`
- `GET /project-events`
- `GET /project-events/{task_id}`
- `GET /tasks/{task_id}/events`
- `GET /tasks/{task_id}/baton-packets`
- `GET /tasks/{task_id}/baton-packets/latest`
- `POST /routing/decide`
- `POST /routing/next`
- `POST /routing/next-action`
- `GET /tasks/{task_id}/routing`
- `POST /runs/execute`
- `POST /runs/execute/stream`
- `GET /runs/providers`
- `POST /memory/lookup`
- `GET /context/{task_id}`
- `POST /context/assemble`
- `GET /context/references/{ref_id}`
- `POST /workspaces`
- `GET /workspaces`
- `GET /workspaces/{workspace_id}`
- `PATCH /workspaces/{workspace_id}`
- `DELETE /workspaces/{workspace_id}`
- `POST /workspaces/{workspace_id}/scan`
- `GET /workspaces/{workspace_id}/files`
- `GET /analyst/digest/{task_id}`
- `POST /analyst/digest`
- `GET /tasks/{task_id}/digest`
- `GET /diagnostics`
- `GET /diagnostics/config`
- `GET /diagnostics/routes`
- `GET /diagnostics/task/{task_id}`
- `POST /autonomy/scan-once`
- `POST /autonomy/tasks/{task_id}/run`
- `POST /autonomy/tasks/{task_id}/approve`
- `POST /autonomy/tasks/{task_id}/reject`

## Migration Lifecycle (Alembic)

Syncore now supports an Alembic migration lifecycle in `services/orchestrator/alembic`.

Run migrations:

```bash
make db-migrate
```

Generate a new revision:

```bash
make db-revision m="add_new_table"
```

## SLO Metrics

Syncore exposes runtime metrics and threshold evaluation endpoints:

- `GET /metrics` (Prometheus text format)
- `GET /metrics/slo` (threshold checks and computed status)

Configurable SLO thresholds:
- `SLO_MAX_HTTP_ERROR_RATE`
- `SLO_MAX_HTTP_P95_LATENCY_MS`
- `SLO_MIN_RUN_SUCCESS_RATE`

### Example payloads

Create task:

```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"title":"Validate local MVP","task_type":"implementation","complexity":"high"}'
```

Create agent run:

```bash
curl -X POST http://localhost:8000/agent-runs \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<TASK_ID>","role":"planner","status":"running","input_summary":"Draft plan"}'
```

Create baton packet:

```bash
curl -X POST http://localhost:8000/baton-packets \
  -H "Content-Type: application/json" \
  -d '{
    "task_id":"<TASK_ID>",
    "from_agent":"planner",
    "to_agent":"coder",
    "summary":"Handoff",
    "payload":{
      "objective":"Ship local prototype",
      "completed_work":["Planned API surface"],
      "constraints":["No AWS in this run"],
      "open_questions":["Need final polish scope"],
      "next_best_action":"Implement core routes",
      "relevant_artifacts":["README.md"]
    }
  }'
```

Route decision:

```bash
curl -X POST http://localhost:8000/routing/decide \
  -H "Content-Type: application/json" \
  -d '{"task_type":"implementation","complexity":"high","requires_memory":true}'
```

Memory lookup:

```bash
curl -X POST http://localhost:8000/memory/lookup \
  -H "Content-Type: application/json" \
  -d '{"task_id":"<TASK_ID>","limit":20}'
```

Context bundle:

```bash
curl http://localhost:8000/context/<TASK_ID>
```

Context reference retrieval:

```bash
curl http://localhost:8000/context/references/<REF_ID>
```

Create workspace:

```bash
curl -X POST http://localhost:8000/workspaces \
  -H "Content-Type: application/json" \
  -d '{
    "name":"Syncore",
    "root_path":"/absolute/path/to/project",
    "runtime_mode":"native",
    "metadata":{}
  }'
```

Scan workspace:

```bash
curl -X POST http://localhost:8000/workspaces/<WORKSPACE_ID>/scan
```

List workspace files safely:

```bash
curl "http://localhost:8000/workspaces/<WORKSPACE_ID>/files?path=.&limit=200"
```

Run execution through Syncore:

```bash
curl -X POST http://localhost:8000/runs/execute \
  -H "Content-Type: application/json" \
  -d '{
    "task_id":"<TASK_ID>",
    "prompt":"Implement the next endpoint and include tests.",
    "target_agent":"coder",
    "target_model":"gpt-4.1-mini",
    "provider":"local_echo",
    "token_budget":1600
  }'
```

Streaming run execution (SSE):

```bash
curl -N -X POST http://localhost:8000/runs/execute/stream \
  -H "Content-Type: application/json" \
  -d '{
    "task_id":"<TASK_ID>",
    "prompt":"Review and summarize current blockers.",
    "target_agent":"reviewer",
    "target_model":"gpt-4.1-mini",
    "provider":"local_echo"
  }'
```

How this run process works:

1. Syncore assembles and optimizes task context first (`/context/assemble` behavior).
2. Large logs/tool outputs are replaced by `ref_id`, with originals stored server-side.
3. Syncore creates an agent run record and executes the prompt via selected provider adapter.
4. Token estimates, refs, and warnings are returned in the run response.
5. Full artifacts remain retrievable later with `GET /context/references/{ref_id}`.

## Sample End-to-End Walkthrough

### One-command canonical flow

```bash
make demo-local
```

What it does:

1. Creates task.
2. Starts planner run.
3. Logs analysis events.
4. Creates planner→coder baton packet.
5. Starts coder run and completes it.
6. Logs completion event.
7. Requests routing decision.
8. Generates analyst digest.
9. Prints inspection URLs and JSON snapshots.

### Inspect results

- API task detail: `http://localhost:8000/tasks/<TASK_ID>`
- API digest: `http://localhost:8000/analyst/digest/<TASK_ID>`
- Web console: `http://localhost:3000/?taskId=<TASK_ID>`
- Workspace console: `http://localhost:3000/workspaces`

## Testing

Run full local validation:

```bash
make check
```

Direct backend tests:

```bash
PYTHONPATH=services/orchestrator:. python3 -m pytest \
  services/orchestrator/tests \
  services/router/tests \
  services/memory/tests \
  services/analyst/tests \
  packages/contracts/python/test_models.py -q
```

## Troubleshooting

### Docker not reachable

- Ensure Docker Desktop is running.
- Ensure WSL integration is enabled for your distro.
- Re-run `docker version` and `docker compose version`.

### Services healthy but DB checks fail

- Verify `POSTGRES_DSN` and `REDIS_URL` in `.env`.
- Confirm compose status: `docker compose ps`.
- Rebuild stack: `make down && make bootstrap`.

### Reset local data

```bash
docker compose down -v
make bootstrap
```

### API validation errors on baton payload

- Baton payload is strongly typed and must include:
  - `objective`
  - `next_best_action`
- See the baton example in this README.

For expanded diagnostics and DB/log inspection commands, see `docs/TROUBLESHOOTING.md`.

## Current Limitations

- Local MVP focuses on one end-to-end workflow, not broad product coverage.
- Authentication and multi-tenant concerns are intentionally out of scope.
- AWS assets are placeholders and not production-ready.
- Provider-specific model execution is intentionally minimal.

## Next Milestone

After local acceptance is fully green, move to staging/AWS alpha readiness:

- secret management hardening
- deployment automation
- cloud persistence validation
- security controls and CI/CD policy tightening

See `docs/LOCAL_VALIDATION.md`, `docs/LOCAL_MVP_CHECKLIST.md`, and `docs/STATUS.md` for latest validation details.
