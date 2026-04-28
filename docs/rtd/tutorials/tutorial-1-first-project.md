# Tutorial 1: First Project End-to-End

This tutorial walks through a complete Syncore flow using a real local repository.

## Outcome

By the end you will have:
- a registered workspace
- a scanned project profile
- at least one task
- at least one agent run
- route and digest outputs

## Step 0: Start Syncore

Native mode:

```bash
cp .env.example .env
make bootstrap-local
make dev-local
```

In a second terminal:

```bash
make install-cli
syncore status
```

Expected: healthy API and service status.

## Step 1: Register your workspace

```bash
syncore workspace add ./my-app --name my-app
syncore workspace list
```

If your project is already registered, this command will return an error or duplicate warning depending on state.

## Step 2: Scan workspace

```bash
syncore workspace scan my-app
```

Review detection output:
- languages
- frameworks
- package managers
- test commands
- docs
- important files

## Step 3: Inspect safe files

```bash
syncore workspace files my-app
```

You should see relative paths only. Secret-like files are blocked.

## Step 4: Create a task

```bash
syncore task create "Audit authentication flow" \
  --workspace my-app \
  --description "Identify auth/session edge cases" \
  --type analysis \
  --complexity medium
```

Then list tasks:

```bash
syncore task list --workspace my-app
```

Copy the returned task ID.

## Step 5: Start an agent run

```bash
syncore run start <TASK_ID> --agent-role backend
syncore run list
```

Task creation and run execution are intentionally separate so operators can control scheduling and model/provider choices.

## Step 6: Request route recommendation

```bash
syncore route <TASK_ID>
```

This returns a deterministic routing decision payload using task characteristics.

## Step 7: Generate digest

```bash
syncore digest <TASK_ID>
```

Digest summarizes task/event signals for quick operator review.

## Step 8: Open interactive TUI

```bash
syncore open my-app
```

Use TUI to inspect task detail, runs, batons, routing, and diagnostics.

## Common failures

- `Connection refused`: orchestrator not running on expected API URL.
- workspace not found: use `syncore workspace list` and verify name/id.
- empty events/digest: run may not have emitted event trail yet.
