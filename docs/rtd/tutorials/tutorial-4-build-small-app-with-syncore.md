# Tutorial 4: Use Syncore to Build a Small App

This tutorial shows the intended Syncore workflow for turning an idea into structured implementation work.

## Goal

Use Syncore to manage a small application build in an existing repository.

Example idea:

```text
Build a tiny notes API with create/read/update/delete endpoints, tests, and a README.
```

## Step 1: Prepare a project directory

```bash
mkdir notes-api
cd notes-api
git init
```

Create any starter files you want, or leave the directory empty for planning.

## Step 2: Register workspace

From the Syncore repo or any terminal with CLI installed:

```bash
syncore workspace add /absolute/path/to/notes-api --name notes-api
syncore workspace scan notes-api
```

At this point Syncore knows where the project lives and can inspect safe files under that root.

## Step 3: Create a planning task

```bash
syncore task create "Plan notes API implementation" \
  --workspace notes-api \
  --type analysis \
  --complexity low
```

Copy the task ID.

## Step 4: Execute planning

Use `local_echo` to test the pipeline or a configured provider for real model output.

```bash
curl -X POST http://localhost:8000/runs/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "prompt": "Plan a minimal notes API with CRUD endpoints, tests, and README updates.",
    "target_agent": "planner",
    "target_model": "local_echo",
    "provider": "local_echo",
    "agent_role": "planner",
    "token_budget": 8000
  }'
```

## Step 5: Record a baton handoff

```bash
curl -X POST http://localhost:8000/baton-packets \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "from_agent": "planner",
    "to_agent": "coder",
    "summary": "Plan ready for implementation",
    "payload": {
      "objective": "Implement notes API CRUD behavior",
      "completed_work": ["Defined resource shape", "Identified test requirements"],
      "constraints": ["Keep implementation minimal", "Include tests"],
      "open_questions": [],
      "next_best_action": "Create implementation task",
      "relevant_artifacts": ["README.md"]
    }
  }'
```

## Step 6: Create implementation task

```bash
syncore task create "Implement notes API CRUD endpoints" \
  --workspace notes-api \
  --type implementation \
  --complexity medium
```

## Step 7: Use TUI for tracking

```bash
syncore open notes-api
```

Use the TUI to inspect tasks, route next action, create digest, and monitor run state.

## Step 8: Validate output

After code changes are made by an agent or developer, record test results as project events:

```bash
curl -X POST http://localhost:8000/project-events \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id": "<TASK_ID>",
    "event_type": "tests.completed",
    "event_data": {
      "command": "pytest",
      "status": "passed"
    }
  }'
```

Then generate a digest:

```bash
syncore digest <TASK_ID>
```

## What Syncore does and does not do in this flow

Syncore does:

- organize tasks and runs
- preserve event history
- hand off context through baton packets
- optimize context for model calls
- provide routing and digest surfaces

Syncore does not automatically guarantee production-quality code from a vague prompt. Good outcomes still require clear tasks, tests, review, and provider configuration.
