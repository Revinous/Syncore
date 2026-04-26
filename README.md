# Syncore Local MVP Operator Guide

Syncore is a local-first orchestration platform prototype where specialized agent roles hand off work through structured baton packets, persist durable state in PostgreSQL, and generate analyst digests from real project events.

This guide is intentionally focused on **local MVP validation only**. It does not add AWS, staging hardening, or production scope.

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
│ PostgreSQL 16         │         │ Redis 7               │
│ durable workflow data │         │ short-lived cache      │
│ tasks/runs/events/... │         │ and coordination       │
└───────────────────────┘         └───────────────────────┘
```

## Repository Layout

- `apps/web` – Next.js local console for workflow visibility.
- `services/orchestrator` – FastAPI API + orchestration service layer.
- `services/memory` – PostgreSQL-backed data store methods.
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
- `docker` + `docker compose`

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
- `ORCHESTRATOR_INTERNAL_URL` – server-side web app API base (Docker internal)
- `POSTGRES_DSN` – orchestrator DB connection string
- `REDIS_URL` – redis connection string
- Provider API keys are intentionally omitted from `.env.example`; add any secrets only in your local `.env`.
- `.env.example` uses placeholder DB credentials; Docker Compose still boots with internal dev defaults for local MVP.

## Local Quickstart

```bash
cp .env.example .env
make bootstrap
```

Then verify:

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
make up             # docker compose up -d --build
make down           # docker compose down
make logs           # tail compose logs
make demo-local     # run canonical local orchestration flow
make test           # backend + frontend tests
make check          # lint + tests + typecheck + build
```

## API Endpoints (Local MVP)

- `GET /health`
- `GET /health/services`
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `POST /agent-runs`
- `PATCH /agent-runs/{run_id}`
- `POST /baton-packets`
- `GET /baton-packets/{task_id}`
- `GET /baton-packets/by-id/{packet_id}`
- `POST /project-events`
- `GET /project-events/{task_id}`
- `POST /routing/decide`
- `POST /routing/next`
- `POST /runs/execute`
- `POST /runs/execute/stream`
- `POST /memory/lookup`
- `GET /context/{task_id}`
- `POST /context/assemble`
- `GET /context/references/{ref_id}`
- `GET /analyst/digest/{task_id}`
- `GET /diagnostics/task/{task_id}`

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
