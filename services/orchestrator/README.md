# Orchestrator Service

FastAPI service that coordinates worker agents and exposes core control-plane APIs.

## Local checks

```bash
python3 -m pytest services/orchestrator/tests -q
python3 -m ruff check services/orchestrator
python3 -m ruff format --check services/orchestrator
```
