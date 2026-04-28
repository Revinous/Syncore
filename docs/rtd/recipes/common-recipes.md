# Common Recipes

Recipes are task-focused procedures. Each one assumes the orchestrator API is reachable at `http://localhost:8000` unless you set `SYNCORE_API_URL`.

## Start native mode from nothing

Use this when you want the fastest local path.

```bash
cd Syncore
cp .env.example .env
make bootstrap-local
make dev-local
```

In another terminal:

```bash
syncore status
```

Expected result:

- API status is healthy.
- Database service is `ok`.
- Redis is `skipped` when `REDIS_REQUIRED=false`.

## Start Docker mode

Use this when you want Postgres and Redis running through Compose.

```bash
cd Syncore
cp .env.example .env
make bootstrap
docker compose ps
```

Expected result:

- web service is exposed on `3000`
- orchestrator service is exposed on `8000`
- postgres and redis containers are running

## Register the current repository as a workspace

```bash
syncore workspace add . --name syncore
syncore workspace scan syncore
syncore workspace files syncore
```

If the CLI was started from outside the repo, pass an absolute path to avoid confusion.

## Open a workspace directly in TUI

```bash
syncore open syncore
```

Shortcut:

```bash
syncore syncore
```

The shortcut resolves the workspace name and opens the same TUI session.

## Create a task and run it

```bash
syncore task create "Review API route coverage" --workspace syncore --type review --complexity medium
syncore task list --workspace syncore
syncore run start <TASK_ID> --agent-role reviewer
syncore run list
```

Task creation records intent. A run records an execution attempt. These are separate so Syncore can support manual review, model selection, queueing, and autonomy.

## Execute a provider-backed run

Use `/runs/execute` when you want a real model/provider execution path rather than just creating an agent-run record.

```bash
curl -X POST http://localhost:8000/runs/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "prompt": "Inspect the workspace and summarize likely test entrypoints.",
    "target_agent": "analyst",
    "target_model": "local_echo",
    "provider": "local_echo",
    "agent_role": "analyst",
    "token_budget": 8000
  }'
```

Use `local_echo` for local plumbing tests. Use configured external providers when you need real model output.

## Generate context and inspect references

```bash
curl -X POST http://localhost:8000/context/assemble \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "target_agent": "coder",
    "target_model": "local_echo",
    "token_budget": 4000
  }'
```

If the response includes `included_refs`, retrieve one:

```bash
curl http://localhost:8000/context/references/<REF_ID>
```

## Check token efficiency

```bash
syncore metrics context
syncore metrics layering
```

Use this after context assembly or run execution has created context bundles.

## Run the canonical demo

```bash
make demo-local
```

The demo validates:

- task creation
- agent run creation
- event creation
- baton creation
- routing
- context assembly
- analyst digest

## Verify before pushing

```bash
make local-test
make check
make docs-build
```

`make check` is broader and includes linting, backend tests, frontend tests, typecheck, and web build.
