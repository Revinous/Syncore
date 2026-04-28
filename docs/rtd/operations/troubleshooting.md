# Troubleshooting

Start with the failing surface, then verify the API, then verify the active runtime mode.

## Fast Triage

Run:

```bash
syncore status
curl http://localhost:8000/health
curl http://localhost:8000/health/services
curl http://localhost:8000/diagnostics/config
```

These commands answer:

- Is the orchestrator reachable?
- Is the database healthy?
- Is Redis required or skipped?
- Which runtime mode and DB backend are active?

## API connection refused

Symptom:

```text
Could not reach Syncore API at http://localhost:8000
```

Likely causes:

- `make dev-local` is not running
- Docker stack is down
- API is on a different port
- stale process crashed after CLI auto-start

Fix native mode:

```bash
make dev-local
```

Fix Docker mode:

```bash
make bootstrap
docker compose ps
```

If CLI auto-start was used, inspect:

```bash
tail -200 .syncore/orchestrator-cli.log
```

## Web UI loads but data is empty

Check:

```bash
curl http://localhost:8000/dashboard/summary
```

Likely causes:

- Web UI points at a different API URL
- you are using a fresh SQLite/Postgres database
- workspace/task records were created in another runtime mode

Fix:

- verify `NEXT_PUBLIC_API_BASE_URL`
- verify `/diagnostics/config`
- recreate or import workspace records in the active backend

## CLI works but TUI shows no tasks

Check:

```bash
syncore workspace list
syncore task list
syncore task list --workspace <workspace-name>
```

Likely causes:

- TUI is scoped to a workspace with no tasks
- task was created without `workspace_id`
- API was restarted against a different database

Fix:

Create a workspace-scoped task:

```bash
syncore task create "Example task" --workspace <workspace-name>
```

## Workspace scan fails

Symptoms:

- `Workspace root not found`
- `Workspace path not found`
- empty metadata

Check:

```bash
syncore workspace show <workspace>
ls -la <root_path>
```

Fix:

- update workspace root path if it moved
- use an absolute path when registering from another directory
- ensure orchestrator process can see the path

## Files are missing from workspace file list

This can be expected.

Syncore hides:

- ignored directories such as `.git`, `node_modules`, `.venv`, `dist`, `build`, `.next`, `target`, `vendor`
- files above the max size threshold
- secret-like files such as `.env`, `*.pem`, `*.key`, `secrets.*`, `credentials.*`

Use this to confirm the API is working:

```bash
curl 'http://localhost:8000/workspaces/<WORKSPACE_ID>/files?path=.&limit=20'
```

## Route exists in docs but returns 404

Check registered routes:

```bash
curl http://localhost:8000/diagnostics/routes
```

Likely causes:

- stale orchestrator process
- old Docker image
- wrong branch

Fix:

Native:

```bash
make dev-local
```

Docker:

```bash
docker compose down
make bootstrap
```

## Context metrics are zero

Likely cause:

No optimized context bundles have been created in the active database.

Generate one:

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

Then:

```bash
syncore metrics context
```

## OpenAI models are empty or auth fails

Check:

```bash
syncore auth openai status
syncore auth openai models
```

Likely causes:

- no local CLI credential
- invalid key
- account does not have access to expected model
- network/provider error

Fix:

```bash
syncore auth openai login
```

Provider auth for CLI model listing is separate from orchestrator provider configuration used by `/runs/execute`.

## Docs build fails

Run:

```bash
make docs-build
```

Common causes:

- invalid YAML in `mkdocs.yml`
- nav entry points to a missing file
- root docs index is missing

Root serving requires:

```text
docs/index.md
```

and:

```yaml
nav:
  - Home: index.md
```
