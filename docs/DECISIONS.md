# Decisions

- Local-first bootstrap before AWS deployment.
- Monorepo structure with phased delivery.
- PostgreSQL as durable memory source of truth.
- Redis for short-lived coordination.
- FastAPI orchestrator follows explicit app-package layout (`app/config.py`, `app/lifecycle.py`, `app/api/routes`).
- Shared contracts live in `packages/contracts` with Python (pydantic) and TypeScript representations.
- Docker Compose uses service health checks and dependency gating for cleaner local startup.
- Routing is deterministic in Phase 2: task type selects worker role, complexity selects model tier.
- Memory persistence uses PostgreSQL JSONB-backed baton/event records with task/time indexes for retrieval.
- Router and memory services stay as explicit modules first; orchestration wiring can expand in later phases.
