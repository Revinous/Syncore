# Status

Initial state: repository seeded.

## Autonomy v1 update (April 28, 2026)

Implemented first-class internal autonomy loop in orchestrator so Syncore can execute new tasks from high-level ideas without manual run orchestration.

### Added
- Internal autonomy service:
  - evaluates new tasks
  - applies routing decisions
  - creates kickoff baton packets
  - executes runs through existing `/runs/execute` service path
  - marks task `completed` on success or `blocked` on failure
  - emits analyst digest metadata event after completion
- API endpoints:
  - `POST /autonomy/scan-once`
  - `POST /autonomy/tasks/{task_id}/run`
- Background loop (config-gated) wired in app lifespan:
  - controlled by `AUTONOMY_ENABLED`
  - cadence via `AUTONOMY_POLL_INTERVAL_SECONDS`
  - fallback model via `AUTONOMY_DEFAULT_MODEL`

### Validation
- Added and passed autonomy tests:
  - `services/orchestrator/tests/test_autonomy.py`
    - scan-once executes a new task end-to-end
    - background loop picks up and completes newly created tasks
- Regression checks passed for orchestrator and CLI/TUI suites.

### Remaining autonomy limitations
- Planning is still single-pass and deterministic; no multi-step replanning loop yet.
- No long-running worker queue with retries/backoff policies beyond current flow.
- No human approval gate between generated plan and execution.

## Autonomy v2 update (April 28, 2026)

Extended autonomy to a staged execution pipeline with retry/backoff safeguards.

### Added
- Stage-based task progression:
  - `plan` -> `execute` -> `review` -> finalize
- Stage events:
  - `autonomy.stage.completed`
  - `autonomy.stage.failed`
  - `autonomy.retry.scheduled`
- Approval gate:
  - optional `requires_approval` preference in `task.preferences`
  - pauses after `plan` before `execute`
  - approve/reject endpoints:
    - `POST /autonomy/tasks/{task_id}/approve`
    - `POST /autonomy/tasks/{task_id}/reject`
  - TUI hotkeys:
    - `y` approve selected task
    - `u` reject selected task
- Retry/backoff:
  - exponential backoff per stage
  - configurable retry budget before task is set to `blocked`

### Configuration
- `AUTONOMY_MAX_RETRIES`
- `AUTONOMY_RETRY_BASE_SECONDS`

### Validation
- Added and passed retry + blocking coverage in:
  - `services/orchestrator/tests/test_autonomy.py`

## Hardening increment (April 28, 2026)

Implemented optional API perimeter controls and safer diagnostics output.

### Added
- Optional API key auth middleware:
  - `API_AUTH_ENABLED`
  - `API_AUTH_TOKEN`
  - header: `x-api-key`
- Optional fixed-window rate limiting middleware:
  - `RATE_LIMIT_ENABLED`
  - `RATE_LIMIT_WINDOW_SECONDS`
  - `RATE_LIMIT_MAX_REQUESTS`
- Diagnostics config redaction:
  - `POSTGRES_DSN` and `REDIS_URL` are masked in `/diagnostics/config`

### Validation
- Added and passed:
  - `services/orchestrator/tests/test_security.py`
  - `services/orchestrator/tests/test_diagnostics.py`

## Local MVP reachability update (April 26, 2026)

Completed an end-to-end reachability pass focused on the local MVP surface.

### Routes now wired and reachable
- Confirmed `services/orchestrator/app/main.py` includes all local MVP routers:
  - `health`, `analyst`
  - `tasks`
  - `agent_runs`
  - `baton_packets`
  - `project_events`
  - `routing`
  - `runs`
  - `memory`
  - `context`
  - `diagnostics`
- Verified live acceptance checks against running orchestrator:
  - `GET /health` -> `200`
  - `POST /tasks` -> `201`
  - `POST /routing/decide` -> `200`
  - `POST /context/assemble` -> `200`

### README consistency
- Confirmed local `README.md` already contains the full **Syncore Local MVP Operator Guide** (not the old one-line bootstrap README).

### DB schema and bootstrap validation
- Confirmed `scripts/init_db.sql` defines:
  - `tasks`
  - `agent_runs`
  - `baton_packets`
  - `project_events`
  - `context_references`
  - `context_bundles`
- Ran clean startup sequence:
  - `docker compose down -v`
  - `make bootstrap`
- Result: PostgreSQL init script executed successfully and all services came up healthy.

### Canonical demo-local result
- Ran `make demo-local`.
- Result: completed successfully through full workflow:
  - task -> agent run -> event -> baton -> routing -> context -> digest
- Verified output URLs and payloads were produced without route/service/payload failures.

### API smoke test coverage
- Added smoke workflow test in `services/orchestrator/tests/test_workflow_api.py`:
  - `test_api_smoke_task_event_baton_context_and_digest`
- Test verifies:
  - create task
  - create event
  - create baton
  - assemble context (`POST /context/assemble`)
  - fetch analyst digest
- Validation status:
  - `make check` passes
  - Backend suite: `43 passed`

### Remaining limitations
- Local-first deterministic MVP only; no auth or multi-tenant isolation yet.
- Context optimization is internal and deterministic; no external proxy runtime.
- Run execution providers are still minimal and not production-hardened.

### Next milestone
- Stabilize local run-execution quality gates:
  - richer failure-mode assertions in demo/test paths
  - improved context resume ergonomics for multi-worker chains
  - staged readiness hardening after local acceptance remains consistently green

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

## Phase 4 milestone execution

Executed Phase 4 only from the runbook prompt.

### 1) Terraform AWS structure
- Added Terraform scaffolding for AWS deployment in `infra/terraform/`:
  - VPC, subnets, routing, and security groups.
  - ECS cluster + Fargate services for orchestrator and web.
  - RDS PostgreSQL placeholder.
  - ElastiCache Redis placeholder.
  - ECR repositories.
  - Secrets Manager placeholder.
- Added staged variable files:
  - `infra/terraform/environments/staging.tfvars`
  - `infra/terraform/environments/production.tfvars`

### 2) CI/CD workflows
- Added build/test workflow: `.github/workflows/build-test.yml`.
- Added image publish workflow: `.github/workflows/publish-images.yml`.
- Added Terraform validation workflow: `.github/workflows/infra-validate.yml`.

### 3) Environment documentation
- Added `docs/ENVIRONMENTS.md` covering local, staging, and production execution.
- Documented runtime expectations, commands, and secret placeholders.

### 4) Local workflow protection
- Preserved local Docker Compose development path.
- Re-ran local bootstrap and health checks after Phase 4 changes.

### 5) Validation run
- `make check` passes.
- `bash scripts/bootstrap.sh` succeeds.
- `curl http://localhost:8000/health` and `curl http://localhost:8000/health/services` succeed.
- `curl http://localhost:8000/analyst/digest/{task_id}` returns typed digest payload.


## Local Prototype Validation runbook execution

Executed the `Syncore_Local_Prototype_Validation_Runbook` against the current repository state.

### Documentation and usability
- Rewrote `README.md` as an operator-first local usage guide.
- Clarified `.env.example` with local defaults and variable purpose.
- Added `docs/LOCAL_VALIDATION.md` with commands, checklist, and readiness decision.

### API completion
- Added full local route surface for tasks, agent runs, baton packets, project events, and routing decisions.
- Kept analyst digest generation backed by persisted project events.
- Added service modules under `services/orchestrator/app/services` to keep business logic separate from route handlers.

### Canonical demo flow
- Added `scripts/demo_local_flow.sh` and `make demo-local`.
- Demo performs: task create -> planner run -> events -> baton handoff -> coder run -> update -> digest.
- Script exits non-zero on failure and prints inspection URLs for API/UI.

### Validation and hardening
- Added API and contract coverage for happy path and failure cases.
- Added end-to-end API workflow test in `services/orchestrator/tests/test_workflow_api.py`.
- Updated DB init schema with `agent_runs` table and relevant indexes.

### Visibility
- Upgraded web home page into a local prototype console.
- Console surfaces health/dependency status, recent tasks, selected task detail, baton history, and digest output.

### Verification run
- `bash scripts/bootstrap.sh` passes.
- `make demo-local` passes.
- `make check` passes.
- `curl /health` and `curl /health/services` pass.

### Current gating
- Local MVP validation checklist is green.
- This run intentionally does not perform AWS apply/hardening tasks.

## Local MVP Productization runbook execution

Executed the `Syncore_Next_Pathway_Runbook` to complete local MVP productization gates.

### API surface and workflow completion
- Added/verified public workflow routes for tasks, runs, baton packets, project events, routing decisions, memory lookup, and context assembly.
- Wired all local MVP routes in orchestrator app startup.
- Added task-level diagnostics endpoint for fast operator checks.

### Deterministic local demo
- Added canonical shell demo runner: `scripts/demo_local_flow.sh`.
- Added payload fixtures under `scripts/payloads/` for task, run, event, baton, routing, and memory requests.
- Fixed JSON id extraction in demo script to correctly parse API responses.

### UI/developer console
- Upgraded `apps/web/pages/index.tsx` into an interactive local operator console.
- Console now supports task creation/loading and displays routing, memory lookup, context bundle, and digest output.

### Documentation and operability
- Updated `README.md` as local MVP operator guide with current route surface and sample calls.
- Added `docs/TROUBLESHOOTING.md` with log, DB inspection, and common failure guidance.
- Added `docs/LOCAL_MVP_CHECKLIST.md` and marked items green only after verification.
- Updated `docs/LOCAL_VALIDATION.md` with latest validation date and endpoint evidence.

### Environment hygiene
- Kept `.env.example` free of provider/API secrets; sensitive values remain local `.env` only.

### Verification run (April 22, 2026)
- `make format` passes.
- `make check` passes.
- `bash scripts/bootstrap.sh` passes.
- `make demo-local` passes with end-to-end task -> route -> events -> baton -> context -> digest flow.

## Run execution process (context-first prompt runtime)

Added a first usable prompt execution path so Syncore can execute user prompts through the internal context optimizer before model invocation.

### What changed
- Added typed run contracts:
  - `RunExecutionRequest`
  - `RunExecutionResponse`
  - `RunStreamEvent`
- Added provider abstraction with deterministic local adapter and optional OpenAI adapter:
  - `services/orchestrator/app/runs/providers.py`
- Added run execution service:
  - `services/orchestrator/app/services/run_execution_service.py`
- Added run APIs:
  - `POST /runs/execute`
  - `POST /runs/execute/stream` (SSE)
- Wired run router into app startup.
- Updated docs/routes in `README.md` and `services/orchestrator/README.md`.
- Updated `.env.example` with local LLM runtime settings (no secrets committed).

### Behavior
- Every run first calls internal optimized context assembly.
- Prompt execution then uses selected provider adapter (`local_echo` by default).
- Agent run state and project events are persisted for started/completed/failed runs.
- Large context artifacts continue to be retrievable via `GET /context/references/{ref_id}`.

### Validation added
- `services/orchestrator/tests/test_run_execution_service.py`
- `services/orchestrator/tests/test_runs_api.py`
- Extended contract schema tests for run request/response models.
