# Workspace Workflow

## Lifecycle

1. Add workspace.
2. Scan workspace.
3. Review metadata.
4. Review safe file index.
5. Create tasks attached to workspace.

## Scanner Behavior

Ignored directories include:
- `.git`
- `node_modules`
- `.venv`
- `dist`
- `build`
- `.next`
- `__pycache__`
- `target`
- `vendor`

Scanner extracts:
- languages
- frameworks
- package managers
- likely test commands
- entrypoints
- docs and important files

## Safe File Access Rules

- normalize path with `pathlib`
- forbid traversal beyond workspace root
- enforce max size threshold
- block sensitive patterns by default
