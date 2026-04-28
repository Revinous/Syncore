# Syncore Documentation

Syncore has one backend source of truth: the FastAPI orchestrator.

All control surfaces use the same API:
- Web UI (`apps/web`)
- CLI (`apps/cli`)
- TUI (`syncore tui`)

## Documentation Map

- **Getting Started**: quick launch for native and docker.
- **Environments**: setup per runtime mode.
- **Interfaces**: function-by-function usage for Web UI, CLI, and TUI.
- **Workflows**: workspace, task/run, context optimization, and autonomy lifecycles.
- **Reference**: endpoint list, command reference, and hotkeys.
- **Operations**: troubleshooting and version/branch docs strategy for Read the Docs.

## Which Path Should You Use?

- Use **Native mode** for solo development and fast iteration.
- Use **Docker mode** for parity with enterprise service topology.
