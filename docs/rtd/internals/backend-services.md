# Backend Service Internals

## Route Layer

Routes under `services/orchestrator/app/api/routes` define HTTP contracts and delegate logic to services/stores.

## Service Layer Responsibilities

- Task service: task lifecycle and associations.
- Run service: run status transitions and result persistence.
- Project events service: timeline persistence and retrieval.
- Baton service: handoff packet persistence.
- Routing service: deterministic next-action recommendation.
- Analyst service: digest generation from stored context.
- Context services: assembly + optimization + reference retrieval.
- Autonomy services: staged task progression and policy enforcement.

## Store Factory

`services/memory` provides backend abstraction so route/service code can run against SQLite (native) or Postgres (docker/enterprise) without API surface changes.

## Compatibility Wrappers

Compatibility endpoints expose task-centric aliases to preserve stable consumer paths while core resources remain modular.
