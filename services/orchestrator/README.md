# Orchestrator Service

FastAPI service that powers the local Syncore orchestration workflow.

## Core local routes
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

## Observability
- Structured JSON logs for app lifecycle and HTTP requests.
- `x-request-id` propagation on every response.

## Local checks

```bash
PYTHONPATH=services/orchestrator:. python3 -m pytest services/orchestrator/tests -q
python3 -m ruff check services/orchestrator
python3 -m ruff format --check services/orchestrator
```
