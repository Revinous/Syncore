# CLI

## Install

- `make install-cli`

## Core Commands

- `syncore status`
- `syncore dashboard`
- `syncore workspace list`
- `syncore workspace add PATH --name NAME`
- `syncore workspace scan WORKSPACE`
- `syncore task list`
- `syncore task create "Task title" --workspace WORKSPACE`
- `syncore run list`
- `syncore run start TASK_ID --agent-role ROLE`
- `syncore diagnostics`
- `syncore metrics context`

## One-command workspace open

- `syncore open WORKSPACE`
- shortcut: `syncore WORKSPACE`

This command ensures services are running, then launches the TUI scoped to that workspace.
