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
