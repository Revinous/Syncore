# Web UI Guide

The Web UI is the browser control panel for teams and operators.

## Start

Native mode:

```bash
make dev-local
```

Docker mode:

```bash
make bootstrap
```

Open:
- `http://localhost:3000`

## Key Screens

### Dashboard

Use for system-level visibility:
- runtime mode and backend
- service health
- counts and recent activity

### Workspaces

Use for project onboarding:
- add workspace
- scan workspace
- inspect detected stack metadata
- inspect important files

### Tasks

Use for work planning:
- create tasks
- filter/list tasks
- navigate to task detail

### Task Detail

Use for execution and diagnostics:
- task metadata
- run history
- event timeline
- baton timeline
- routing decision
- digest

### Agent Runs

Use for execution monitoring:
- run status
- role
- timestamps
- result links

### Diagnostics

Use for system debugging:
- route inventory
- runtime config
- backend service state

## API Base Configuration

Set `NEXT_PUBLIC_API_BASE_URL` to target orchestrator endpoint for your environment.
