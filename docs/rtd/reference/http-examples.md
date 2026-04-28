# HTTP Examples

This page gives copy-pasteable examples for the main API flows. Replace angle-bracket IDs such as `<TASK_ID>` with values returned by earlier API calls.

## Health

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/services
```

Use these first whenever a CLI, TUI, or Web UI request fails.

## Create a workspace

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

The `root_path` must exist on the machine running the orchestrator.

## Scan a workspace

```bash
curl -X POST http://localhost:8000/workspaces/<WORKSPACE_ID>/scan
```

The scan result includes languages, frameworks, package managers, test commands, docs, entrypoints, and important files.

## List safe workspace files

```bash
curl 'http://localhost:8000/workspaces/<WORKSPACE_ID>/files?path=.&limit=500'
```

The response contains relative paths only. Secret-like files and ignored directories are omitted.

## Create a task

```bash
curl -X POST http://localhost:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{
    "title": "Audit the login flow",
    "task_type": "analysis",
    "complexity": "medium",
    "workspace_id": "<WORKSPACE_ID>"
  }'
```

Valid `task_type` values:

- `analysis`
- `implementation`
- `integration`
- `review`
- `memory_retrieval`
- `memory_update`

Valid `complexity` values:

- `low`
- `medium`
- `high`

## Start an agent run record

```bash
curl -X POST http://localhost:8000/agent-runs \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "role": "coder",
    "status": "queued",
    "input_summary": "Initial implementation pass"
  }'
```

This creates a durable run record. Use `/runs/execute` for provider execution.

## Execute a run

```bash
curl -X POST http://localhost:8000/runs/execute \
  -H 'Content-Type: application/json' \
  -H 'x-idempotency-key: login-audit-001' \
  -d '{
    "task_id": "<TASK_ID>",
    "prompt": "Analyze the task and produce the next implementation plan.",
    "target_agent": "planner",
    "target_model": "local_echo",
    "provider": "local_echo",
    "agent_role": "planner",
    "token_budget": 8000,
    "max_output_tokens": 1200,
    "temperature": 0.2
  }'
```

The idempotency key prevents duplicate execution for repeated client attempts.

## Stream a run

```bash
curl -N -X POST http://localhost:8000/runs/execute/stream \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "prompt": "Summarize current task state.",
    "target_agent": "analyst",
    "target_model": "local_echo",
    "provider": "local_echo"
  }'
```

The stream uses server-sent events.

## Create a project event

```bash
curl -X POST http://localhost:8000/project-events \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "event_type": "analysis.started",
    "event_data": {
      "source": "manual",
      "note": "Started analysis from HTTP example"
    }
  }'
```

Events are the durable timeline used by diagnostics and digest generation.

## Create a baton packet

```bash
curl -X POST http://localhost:8000/baton-packets \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "from_agent": "planner",
    "to_agent": "coder",
    "summary": "Planner handed off implementation plan",
    "payload": {
      "objective": "Implement the login audit findings",
      "completed_work": ["Identified session middleware entrypoint"],
      "constraints": ["Do not change auth token format"],
      "open_questions": ["Confirm refresh-token expiry behavior"],
      "next_best_action": "Patch middleware tests",
      "relevant_artifacts": ["services/auth/middleware.py"]
    }
  }'
```

## Route next action

```bash
curl -X POST http://localhost:8000/routing/next-action \
  -H 'Content-Type: application/json' \
  -d '{
    "task_type": "implementation",
    "complexity": "medium",
    "requires_memory": true
  }'
```

## Assemble optimized context

```bash
curl -X POST http://localhost:8000/context/assemble \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "target_agent": "coder",
    "target_model": "local_echo",
    "token_budget": 8000
  }'
```

## Retrieve full context reference

```bash
curl http://localhost:8000/context/references/<REF_ID>
```

## Generate digest

```bash
curl -X POST http://localhost:8000/analyst/digest \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "limit": 50
  }'
```

## Inspect diagnostics

```bash
curl http://localhost:8000/diagnostics
curl http://localhost:8000/diagnostics/config
curl http://localhost:8000/diagnostics/routes
curl http://localhost:8000/diagnostics/task/<TASK_ID>
```
