# Status

Initial state: repository seeded.

## Phase 1 bootstrap execution

Completed the requested Phase 1 sequence from the runbook prompt.

### 1) Repository structure validation
- Verified monorepo layout and filled missing files/directories.
- Added service/app docs and shared contracts layout.

### 2) Local developer setup improvements
- Updated `docker-compose.yml` to use health checks and healthy dependency ordering.
- Updated `.env.example` with `NEXT_PUBLIC_API_BASE_URL`.
- Improved bootstrap scripts to wait for PostgreSQL and orchestrator health.
- Verified `bash scripts/bootstrap.sh` brings up `postgres`, `redis`, `orchestrator`, and `web`.

### 3) FastAPI orchestrator expansion
- Refactored into app package structure under `services/orchestrator/app/`.
- Added configuration (`pydantic-settings`), lifecycle wiring, and a typed `/health` route.
- Added backend tests for health endpoint behavior.

### 4) Next.js shell expansion
- Added environment-aware API base config in `apps/web/lib/config.ts`.
- Updated landing page to display API base URL and load orchestrator health.
- Added frontend smoke test and TypeScript project config.

### 5) Dependency manifests and scripts
- Added backend dev dependencies and `pyproject.toml` for `pytest`/`ruff` config.
- Added frontend scripts for lint/typecheck/build/smoke test.
- Updated root `Makefile` with `format`, `lint`, `test`, and `check` targets.

### 6) Typed contracts
- Added typed contracts for tasks, baton packets, and project events:
  - Python pydantic models in `packages/contracts/python/models.py`
  - TypeScript interfaces in `packages/contracts/ts/index.ts`
- Added contract validation tests.

### 7) Validation run
- `make check` passes.
- `bash scripts/bootstrap.sh` succeeds.
- `curl http://localhost:8000/health` returns `{"status":"ok","service":"orchestrator","environment":"development"}`.
- `curl http://localhost:3000` returns the web shell page.

## Phase 2 milestone execution

Executed Phase 2 only from the runbook prompt.

### 1) Baton packet contracts
- Added explicit create/read packet schemas with stronger defaults and validation:
  - `BatonPacketCreate`
  - `BatonPacket`

### 2) Task, event, and memory schemas
- Expanded schemas for task typing and complexity (`TaskType`, `ComplexityLevel`, `TaskCreate`, `Task`).
- Added event and memory request schemas (`ProjectEventCreate`, `MemoryLookupRequest`).
- Added TypeScript equivalents for all key schemas in `packages/contracts/ts/index.ts`.

### 3) Routing policy service
- Implemented first deterministic routing policy engine in `services/router/policy.py`.
- Policy chooses:
  - Worker role based on task type.
  - Model tier based on complexity.
  - Reasoning note when memory context is required.

### 4) Memory service (PostgreSQL-backed)
- Implemented `MemoryStore` in `services/memory/store.py` with methods to:
  - Persist baton packets to PostgreSQL.
  - Retrieve baton packets by task id.
  - Persist project events to PostgreSQL.
  - Retrieve project events by task id.
- Updated `scripts/init_db.sql` with task schema fields and retrieval indexes.

### 5) Tests added
- Contract validation coverage expanded in `packages/contracts/python/test_models.py`.
- Routing decision tests added in `services/router/tests/test_policy.py`.
- Memory store unit tests added in `services/memory/tests/test_store.py`.

### 6) Validation run
- `make check` passes (ruff, pytest, frontend smoke, typecheck, next build).
- Backend test suite: 13 passed.
- Orchestrator health remains green at `http://localhost:8000/health`.

## Phase 3 milestone execution

Executed Phase 3 only from the runbook prompt.

### 1) Analyst service module
- Added dedicated analyst service module in `services/analyst/digest.py`.
- Implemented deterministic executive digest generation from project events.
- Added analyst service tests in `services/analyst/tests/test_digest.py`.

### 2) Analyst digest endpoint
- Added `GET /analyst/digest/{task_id}` endpoint.
- Endpoint loads task events via `MemoryStore` and returns typed `ExecutiveDigest` response.
- Added endpoint tests for successful digest output and memory-store failure handling.

### 3) Observability basics
- Added structured JSON logging utilities in `services/orchestrator/app/observability.py`.
- Added request middleware that:
  - Preserves incoming `x-request-id` or generates one.
  - Returns request id in response headers.
  - Logs structured request metrics (`method`, `path`, `status_code`, `duration_ms`).
- Added observability tests for request-id behavior.

### 4) Service-level health checks
- Expanded health API with `GET /health/services`.
- Health check now reports per-dependency status for PostgreSQL and Redis.
- Added tests for healthy and degraded dependency scenarios.

### 5) Runtime integration and config updates
- Updated orchestrator Docker image to include shared contracts plus analyst and memory modules.
- Updated Compose orchestrator environment to use container-local dependency addresses:
  - `POSTGRES_DSN=postgresql://agentos:agentos@postgres:5432/agentos`
  - `REDIS_URL=redis://redis:6379/0`
- Updated `.env.example` with explicit `POSTGRES_DSN`.

### 6) Validation run
- `make check` passes.
- Backend test suite: 23 passed.
- `bash scripts/bootstrap.sh` succeeds.
- `curl http://localhost:8000/health/services` reports dependency health.
- `curl http://localhost:8000/analyst/digest/{task_id}` returns executive digest payload.
