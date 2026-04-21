# Memory Service

Phase 2 memory layer for storing and retrieving baton packets and project events in PostgreSQL.

## Scope
- Persist baton packet handoffs.
- Persist project event timeline records.
- Retrieve records by task id with bounded limits.

## Local tests

```bash
PYTHONPATH=. python3 -m pytest services/memory/tests -q
```
