# Architecture Standards

Syncore uses a layered architecture with a ratchet against oversized modules.

## Principles

- Routes are adapters.
- Services own domain behavior.
- CLI entrypoints are wiring layers.
- Web pages compose hooks and panels.
- Existing large files must shrink over time, not grow.

## Current Guardrails

- Route modules should stay thin and avoid domain file/report assembly.
- New service modules should stay focused and below the standard size limits.
- `apps/cli/syncore_cli/main.py` should remain a wiring layer.
- Major operator pages should use hooks and focused components.

## Enforcement

Run:

```bash
make architecture-check
```

This checks for:
- route-local report/file-loading patterns
- growth of known oversized modules beyond their current ratchet baseline
- new files crossing the standard line-count limits

## Why This Exists

Syncore already has enough capability. The risk is structural regression:
- oversized orchestration files
- fat route modules
- page-level mini-apps
- CLI entrypoint re-growth

The architecture check is there to stop that drift before it accumulates.
