# System Architecture

## Logical Components

- `apps/web`: Next.js browser control panel.
- `apps/cli`: Typer + Rich + Textual command and interactive interface.
- `services/orchestrator`: FastAPI backend and orchestration services.
- `services/memory`: store abstraction and backend-specific implementations.
- `services/router`: routing policy logic.
- `services/analyst`: digest logic.
- `packages/contracts`: shared data contracts.

## High-Level Request Flow

1. User interaction occurs via Web UI, CLI, or TUI.
2. Client sends request to orchestrator HTTP API.
3. Route handler validates input and calls service layer.
4. Service layer reads/writes through store abstraction.
5. Optional downstream logic executes (routing, context optimization, digest, autonomy).
6. API response is returned to client.

## Single-Backend Rule

There is no separate backend for CLI/TUI/Web. This eliminates split-brain behavior and ensures identical data semantics across interfaces.
