# Orchestrator Service

FastAPI service that coordinates worker agents and exposes control-plane APIs.

## Endpoints
- `GET /health` basic service health
- `GET /health/services` dependency-level health (PostgreSQL and Redis)
- `GET /analyst/digest/{task_id}` executive digest based on project events

## Observability
- Structured JSON log events for startup, shutdown, and HTTP requests
- Per-request `x-request-id` support (accepts inbound ID or generates one)

## Local checks

```bash
python3 -m pytest services/orchestrator/tests -q
python3 -m ruff check services/orchestrator
python3 -m ruff format --check services/orchestrator
```
