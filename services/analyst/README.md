# Analyst Service

Phase 3 analyst module for converting project events into executive-readable digests.

## Scope
- Consume structured `ProjectEvent` records.
- Generate a concise executive digest with highlights, risks, and event breakdown.
- Keep summarization deterministic and easy to inspect.

## Local tests

```bash
PYTHONPATH=. python3 -m pytest services/analyst/tests -q
```
