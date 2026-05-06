# CLI Guide

The Syncore CLI is the fastest way to automate repeatable workflows.

## Setup

```bash
make install-cli
export SYNCORE_API_URL=http://localhost:8000
```

## Command Families

- status and diagnostics
- workspace management
- task management
- run management
- routing and digest
- metrics and provider/auth operations

## Status and Diagnostics

```bash
syncore status
syncore dashboard
syncore diagnostics
```

Use `--json` where available when integrating with shell scripts.

## Workspace Commands

Create:

```bash
syncore workspace add ./my-app --name my-app
```

List/show:

```bash
syncore workspace list
syncore workspace show my-app
```

Scan/files:

```bash
syncore workspace scan my-app
syncore workspace files my-app
```

## Task Commands

Create task:

```bash
syncore task create "Analyze auth flow" \
  --workspace my-app \
  --description "Trace login/session path" \
  --type analysis \
  --complexity medium \
  --provider openai \
  --model gpt-5.4
```

Inspect:

```bash
syncore task list
syncore task show <TASK_ID>
```

Model switch:

```bash
syncore task switch-model <TASK_ID> --provider openai --model gpt-5.5
```

Set autonomy preferences on a task:

```bash
syncore task set-prefs <TASK_ID> \
  --agent-role reviewer \
  --provider openai \
  --model gpt-5.4 \
  --prompt "Run implementation then execute tests and summarize failures." \
  --requires-approval \
  --sdlc-enforce
```

`--sdlc-enforce` enables stricter SDLC checklist gating in the autonomy loop for that task.

## Run Commands

```bash
syncore run list
syncore run start <TASK_ID> --agent-role backend
syncore run result <RUN_ID>
syncore run cancel <RUN_ID>
syncore run resume <RUN_ID>
```

## Task-Centric Shortcuts

```bash
syncore events <TASK_ID>
syncore baton <TASK_ID>
syncore route <TASK_ID>
syncore digest <TASK_ID>
```

## Providers/Auth/Metrics

```bash
syncore providers
syncore auth openai login
syncore auth openai models
syncore metrics context
```

## Open Shortcut

```bash
syncore open my-app
```

Use the explicit `syncore open <workspace>` form for workspace startup.

## Error Behavior

If API is offline, CLI returns readable connection errors instead of Python stack traces for normal user cases.
