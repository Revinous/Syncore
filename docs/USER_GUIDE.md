# Syncore User Guide

This guide is the beginner-friendly manual for using Syncore end to end.

It covers:
- what Syncore is
- how to install and start it
- how to use Web UI, CLI, and TUI
- how tasks, runs, batons, events, routing, and digests work together
- how context optimization and token savings work
- common workflows and troubleshooting

## 1. What Syncore Is

Syncore is an orchestration system for agent workflows.

Core idea:
1. You register a workspace (a local repo/folder).
2. You create a task.
3. Syncore coordinates work through agent runs.
4. State is persisted as events, baton packets, and run records.
5. You inspect/drive everything from API, Web UI, or CLI/TUI.

Syncore has one backend source of truth:
- FastAPI orchestrator (`services/orchestrator`)

Control surfaces:
- Web UI (`apps/web`)
- CLI/TUI (`apps/cli`)

## 2. Core Concepts

### Workspace
A registered project directory Syncore can scan and operate against.

### Task
A unit of work. Example: "Implement auth endpoint with tests".

### Agent Run
Execution record for a role (planner/coder/reviewer/etc).

### Project Event
Immutable timeline events that describe what happened.

### Baton Packet
Structured handoff payload between agents.

### Routing Decision
Decision about next worker role/model tier.

### Analyst Digest
Task summary generated from events.

### Context Optimization
Before model execution, Syncore assembles context and optimizes it to reduce token usage while preserving critical constraints.

## 3. Runtime Modes

### Native Mode (recommended for solo dev)
- DB backend: SQLite
- Redis: optional/off by default
- No Docker required

### Docker Mode
- DB backend: PostgreSQL
- Redis enabled
- Useful for team-like local stacks

## 4. Prerequisites

- `python3` 3.10+
- `node` 20+
- `npm`
- `uv`
- optional for Docker mode: `docker`, `docker compose`

## 5. Quick Start (Native)

```bash
cd Syncore
cp .env.example .env
make bootstrap-local
make dev-local
```

Health check:

```bash
curl http://localhost:8000/health
```

Open Web UI:
- `http://localhost:3000`

Install global CLI command:

```bash
make install-local
```

Then verify:

```bash
syncore status
```

## 6. First Real Workflow

### Step 1: Register workspace

```bash
syncore workspace add ./my-project --name my-project
syncore workspace list
```

### Step 2: Scan workspace

```bash
syncore workspace scan my-project
syncore workspace files my-project
```

### Step 3: Create task

```bash
syncore task create "Build authentication flow" --workspace my-project --type implementation --complexity medium
syncore task list
```

### Step 4: Start run

```bash
syncore run start <TASK_ID> --agent-role coder
syncore run list
```

### Step 5: Inspect task

```bash
syncore task show <TASK_ID>
syncore events <TASK_ID>
syncore baton <TASK_ID>
syncore digest <TASK_ID>
```

## 7. Using the TUI

Start directly on a workspace:

```bash
syncore open my-project
```

Useful hotkeys:
- `q` quit
- `r` refresh
- `d` dashboard
- `w` workspaces
- `t` tasks
- `a` runs
- `x` diagnostics
- `c` metrics
- `n` new task
- `p` start run
- `e` execute task
- `o` route next action
- `g` generate digest
- `z` toggle autonomy

## 8. Using the Web UI

Main pages:
- `/` dashboard
- `/workspaces`
- `/tasks`
- `/tasks/[taskId]`
- `/runs`
- `/diagnostics`

Dashboard includes context efficiency and layering rollout info.

## 9. Context Optimization and Savings

Syncore context optimizer pipeline:
1. assemble task + baton + events + memory
2. preserve critical constraints verbatim
3. compress/summarize low-value bulk
4. replace large logs/tool output with references
5. store originals for retrieval

Key endpoint:
- `POST /context/assemble`
- `GET /context/references/{ref_id}`

Savings metrics:
- `GET /metrics/context-efficiency`
- CLI: `syncore metrics context`

Layering rollout (L0/L1/L2):
- `CONTEXT_LAYERING_ENABLED`
- `CONTEXT_LAYERING_DUAL_MODE`
- `CONTEXT_LAYERING_FALLBACK_THRESHOLD_PCT`
- `CONTEXT_LAYERING_FALLBACK_MIN_SAMPLES`

Profile-level rollout stats:
- CLI: `syncore metrics layering`

## 10. Autonomy Mode

Autonomy allows staged execution loops with quality gates.

Enable in `.env`:
- `AUTONOMY_ENABLED=true`

Useful API endpoints:
- `POST /autonomy/scan-once`
- `POST /autonomy/tasks/{task_id}/run`
- `POST /autonomy/tasks/{task_id}/approve`
- `POST /autonomy/tasks/{task_id}/reject`

Use with operator oversight.

## 11. Run Execution

Non-streaming:
- `POST /runs/execute`

Streaming:
- `POST /runs/execute/stream`

Providers endpoint:
- `GET /runs/providers`

Queue endpoints:
- `POST /runs/queue/enqueue`
- `POST /runs/queue/scan-once`

## 12. Recommended Daily Workflow

1. `syncore open <workspace>`
2. create/select task
3. route + run + inspect events
4. check digest
5. check `syncore metrics context`
6. check `syncore metrics layering` during rollout

## 13. Important Commands Reference

```bash
# startup
make bootstrap-local
make dev-local

# validation
make check
make local-test
make demo-local

# CLI status
syncore status
syncore dashboard
syncore diagnostics

# workspace
syncore workspace add ./repo --name repo
syncore workspace list
syncore workspace scan repo
syncore workspace files repo

# tasks
syncore task create "Task title" --workspace repo
syncore task list
syncore task show <TASK_ID>

# runs
syncore run list
syncore run start <TASK_ID> --agent-role coder
syncore run result <RUN_ID>

# analytics/metrics
syncore digest <TASK_ID>
syncore metrics context
syncore metrics layering

# TUI
syncore open repo
syncore tui
```

## 14. Troubleshooting

### `Connection refused`
API is not running.

Fix:
- run `make dev-local`
- or `syncore open <workspace>`

### `syncore <command>` routes incorrectly
Reinstall launcher:

```bash
make install-local
```

### Health is degraded
Check:
- `curl http://localhost:8000/health/services`
- verify `.env` backend settings

### Reset native DB

```bash
rm -f .syncore/syncore.db
make db-local-init
```

### Reset docker data

```bash
docker compose down -v
make bootstrap
```

## 15. Safety and Expectations

What Syncore can do now:
- orchestrate real local workflows with durable state
- optimize context and report savings
- support autonomy loops with guardrails

What still needs operator involvement:
- final architecture decisions
- production release governance
- external service credentials/secrets management

## 16. Where to Look Next

- `README.md` for operator quick commands
- `docs/TROUBLESHOOTING.md`
- `docs/STATUS.md` for current phase progress
- `services/orchestrator/app/api/routes` for endpoint surface
