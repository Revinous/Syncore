# API Endpoints

## Health
- `GET /health`
- `GET /health/services`

## Dashboard
- `GET /dashboard/summary`

## Workspaces
- `POST /workspaces`
- `GET /workspaces`
- `GET /workspaces/{workspace_id}`
- `PATCH /workspaces/{workspace_id}`
- `DELETE /workspaces/{workspace_id}`
- `POST /workspaces/{workspace_id}/scan`
- `GET /workspaces/{workspace_id}/files`

## Tasks
- `POST /tasks`
- `GET /tasks`
- `GET /tasks/{task_id}`
- `PATCH /tasks/{task_id}`

## Agent Runs
- `POST /agent-runs`
- `GET /agent-runs`
- `GET /agent-runs/{run_id}`
- `PATCH /agent-runs/{run_id}`

## Events / Batons / Routing / Analyst
- `POST /project-events`
- `GET /project-events`
- `GET /tasks/{task_id}/events`
- `POST /baton-packets`
- `GET /tasks/{task_id}/baton-packets`
- `GET /tasks/{task_id}/baton-packets/latest`
- `POST /routing/next-action`
- `GET /tasks/{task_id}/routing`
- `POST /analyst/digest`
- `GET /tasks/{task_id}/digest`
