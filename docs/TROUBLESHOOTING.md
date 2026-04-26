# Troubleshooting (Local MVP)

This document helps operators diagnose common local failures without reading source code first.

## Quick health checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/services
docker compose ps
```

## Check logs

```bash
docker compose logs -f --tail=200 orchestrator
docker compose logs -f --tail=200 web
docker compose logs -f --tail=200 postgres
docker compose logs -f --tail=200 redis
```

## Database inspection

Open `psql`:

```bash
docker compose exec -T postgres psql -U agentos -d agentos
```

Useful queries:

```sql
SELECT id, title, status, task_type, complexity, created_at
FROM tasks
ORDER BY created_at DESC
LIMIT 20;

SELECT id, task_id, role, status, created_at
FROM agent_runs
ORDER BY created_at DESC
LIMIT 20;

SELECT id, task_id, from_agent, to_agent, created_at
FROM baton_packets
ORDER BY created_at DESC
LIMIT 20;

SELECT id, task_id, event_type, created_at
FROM project_events
ORDER BY created_at DESC
LIMIT 20;
```

## Common issues

### API returns connection errors
- Ensure services are up: `make bootstrap`
- Verify ports `8000`, `3000`, `5432`, `6379` are not occupied by other processes.

### DB schema mismatch after pulling latest changes
- Re-apply schema: `bash scripts/bootstrap.sh`
- If still broken, reset local volumes (destructive):

```bash
docker compose down -v
bash scripts/bootstrap.sh
```

### Demo flow fails
- Run health checks first.
- Confirm payload files exist under `scripts/payloads`.
- Run with shell tracing for quick pinpointing:

```bash
bash -x scripts/demo_local_flow.sh
```

### Baton or context retrieval returns 404
- Verify task exists: `curl http://localhost:8000/tasks/<TASK_ID>`
- Verify baton packets for task: `curl http://localhost:8000/baton-packets/<TASK_ID>`
- Verify project events for task: `curl http://localhost:8000/project-events/<TASK_ID>`

### Frontend shows stale/empty data
- Reload with explicit task id: `http://localhost:3000/?taskId=<TASK_ID>`
- Confirm frontend API base:

```bash
grep -E 'NEXT_PUBLIC_API_BASE_URL|ORCHESTRATOR_INTERNAL_URL' .env
```

## Diagnostics endpoint

Use this endpoint for a compact task-level state snapshot:

```bash
curl http://localhost:8000/diagnostics/task/<TASK_ID>
```

It reports whether task exists and counts of runs, baton packets, and events.
