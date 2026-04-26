# Memory Service

Memory layer for storing and retrieving baton packets, project events, and context artifacts.

Backends:
- PostgreSQL (`services/memory/store.py`) for Docker/enterprise mode.
- SQLite (`services/memory/sqlite_store.py`) for solo native mode.

## Scope
- Persist baton packet handoffs.
- Persist project event timeline records.
- Retrieve records by task id with bounded limits.

## Local tests

```bash
PYTHONPATH=. python3 -m pytest services/memory/tests -q
```
