# CLI and TUI Internals

## CLI Stack

- `Typer` for command tree
- `httpx` API client wrapper
- `Rich` render utilities for tables/panels/json

## TUI Stack

- `Textual` for interactive layout, hotkeys, and view switching
- API polling loop for state refresh
- graceful offline handling with status indicators

## Auto-start behavior

`syncore open <workspace>` and `syncore tui` can auto-start local API only for local-native configuration.

Auto-start guardrails:
- host must be localhost/127.0.0.1
- `SYNCORE_RUNTIME_MODE=native`
- `SYNCORE_DB_BACKEND=sqlite`

If guardrails fail, CLI returns explicit guidance instead of silently mutating environment assumptions.
