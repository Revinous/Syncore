# What Is Syncore

Syncore is an orchestration platform for structured software work across tasks, runs, events, baton handoffs, routing decisions, context optimization, and analyst summarization.

It is designed around one core rule: **all control surfaces share one backend API**.

## Control Surfaces

- Web UI for operator visibility and dashboards.
- CLI for deterministic command-driven workflows.
- TUI for interactive terminal operations.

All three consume the same FastAPI orchestrator endpoints.

## Core Capabilities

- Workspace registration and repository scanning.
- Task lifecycle management.
- Agent run lifecycle management.
- Durable project event logging.
- Baton packet handoff tracking.
- Routing decision generation for next actions.
- Analyst digest generation.
- Context optimization with token-efficiency metrics.
- Optional autonomy loops with staged execution and quality gates.

## Runtime Modes

- Native mode for local development (`sqlite`, optional redis).
- Docker mode for enterprise-like topology (`postgres`, `redis`, web + api services).

## Data Ownership

Syncore persists operational state in the configured database backend. The API is the source of truth for reads and writes. CLI/TUI/Web UI must not mutate data directly via DB connections.
