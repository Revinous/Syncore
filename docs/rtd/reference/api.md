# API Reference

This chapter provides operational endpoint coverage with example request patterns.

## Health

- `GET /health`
- `GET /health/services`

Example:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/services
```

## Dashboard

- `GET /dashboard/summary`

```bash
curl http://localhost:8000/dashboard/summary
```

## Workspace Endpoints

- `POST /workspaces`
- `GET /workspaces`
- `GET /workspaces/{workspace_id}`
- `PATCH /workspaces/{workspace_id}`
- `DELETE /workspaces/{workspace_id}`
- `POST /workspaces/{workspace_id}/scan`
- `GET /workspaces/{workspace_id}/files`

Create example:

```bash
curl -X POST http://localhost:8000/workspaces \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "my-app",
    "root_path": "/home/user/my-app",
    "repo_url": null,
    "branch": null,
    "runtime_mode": "native",
    "metadata": {}
  }'
```

## Task Endpoints

- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}`
- `POST /tasks/{task_id}/model-switch`

Create example:

```bash
curl -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Implement auth endpoint",
    "description": "Add token verification path",
    "workspace_id": "<workspace-id>",
    "complexity": "medium",
    "preferred_provider": "openai",
    "preferred_model": "gpt-5.4"
  }'
```

## Agent Run Endpoints

- `POST /agent-runs`
- `GET /agent-runs`
- `GET /agent-runs/{run_id}`
- `PATCH /agent-runs/{run_id}`
- `GET /agent-runs/{run_id}/result`
- `POST /agent-runs/{run_id}/cancel`
- `POST /agent-runs/{run_id}/resume`

## Project Event Endpoints

- `POST /project-events`
- `GET /project-events`
- `GET /project-events/{task_id}`
- `GET /project-events/by-task/{task_id}`

## Baton Packet Endpoints

- `POST /baton-packets`
- `GET /baton-packets`
- `GET /baton-packets/{task_id}`
- `GET /baton-packets/by-id/{packet_id}`
- `GET /baton-packets/task/{task_id}/latest`

## Routing Endpoints

- `POST /routing/decide`
- `POST /routing/next`
- `POST /routing/next-action`
- `GET /routing/task/{task_id}`

## Context Endpoints

- `GET /context/{task_id}`
- `POST /context/assemble`
- `GET /context/references/{ref_id}`

Assemble example:

```bash
curl -X POST http://localhost:8000/context/assemble \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<task-id>",
    "target_agent": "backend",
    "target_model": "gpt-5.4",
    "token_budget": 8000
  }'
```

## Analyst Endpoints

- `GET /analyst/digest/{task_id}`
- `POST /analyst/digest`

## Diagnostics Endpoints

- `GET /diagnostics`
- `GET /diagnostics/config`
- `GET /diagnostics/routes`
- `GET /diagnostics/task/{task_id}`

## Metrics Endpoints

- `GET /metrics`
- `GET /metrics/slo`
- `GET /metrics/context-efficiency`

## Memory Endpoint

- `POST /memory/lookup`

## Runs Utility Endpoints

- `POST /runs/execute`
- `POST /runs/execute/stream`
- `GET /runs/providers`
- `POST /runs/queue/enqueue`
- `POST /runs/queue/scan-once`

## Compatibility Endpoints

- `GET /tasks/{task_id}/events`
- `GET /tasks/{task_id}/baton-packets`
- `GET /tasks/{task_id}/baton-packets/latest`
- `GET /tasks/{task_id}/routing`
- `GET /tasks/{task_id}/digest`

## Auth Header (Optional)

If API auth is enabled, pass:

- header `x-api-key: <token>`
