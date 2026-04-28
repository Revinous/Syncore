# CLI Command Reference

## Status and Dashboard
- `syncore status`
- `syncore dashboard`

## Workspaces
- `syncore workspace list`
- `syncore workspace add PATH --name NAME`
- `syncore workspace show WORKSPACE`
- `syncore workspace scan WORKSPACE`
- `syncore workspace files WORKSPACE`

## Tasks
- `syncore task list`
- `syncore task create "TITLE" --workspace WORKSPACE`
- `syncore task show TASK_ID`

## Runs
- `syncore run list`
- `syncore run start TASK_ID --agent-role ROLE`
- `syncore run result RUN_ID`

## Other
- `syncore diagnostics`
- `syncore metrics context`
- `syncore tui`
- `syncore open WORKSPACE`
