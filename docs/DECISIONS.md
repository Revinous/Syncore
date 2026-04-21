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
- Phase 3 uses a dedicated analyst module to generate deterministic, auditable executive digests from structured events.
- Observability baseline includes structured logs and end-to-end request IDs on every HTTP response.
- Service health is split into basic app liveness (`/health`) and dependency readiness (`/health/services`).
- Container runtime for orchestrator explicitly uses service DNS (`postgres`, `redis`) for internal dependency connectivity.
- Phase 4 introduces AWS deployment scaffolding (Terraform + CI workflows) while preserving local-first operation as a non-negotiable workflow.
- Terraform in Phase 4 is intentionally placeholder-oriented and requires environment-specific hardening before production apply.
