# Router Service

Phase 2 routing policy engine for assigning worker role and model tier.

## Scope
- Accept typed routing requests.
- Produce deterministic routing decisions.
- Keep policy explicit and easy to audit.

## Local tests

```bash
PYTHONPATH=. python3 -m pytest services/router/tests -q
```
