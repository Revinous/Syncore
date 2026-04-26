# Local MVP Checklist

Validation date: April 22, 2026

## Scope gate

- [x] Local MVP only (no new AWS/Terraform expansion in this runbook)

## Operator experience

- [x] `README.md` is a complete local operator guide
- [x] Repo structure and local workflow are documented
- [x] Sample API commands and payloads are documented

## Public orchestrator APIs

- [x] `POST /tasks`
- [x] `GET /tasks`
- [x] `GET /tasks/{task_id}`
- [x] `POST /agent-runs`
- [x] `PATCH /agent-runs/{run_id}`
- [x] `POST /baton-packets`
- [x] `GET /baton-packets/{task_id}`
- [x] `POST /project-events`
- [x] `GET /project-events/{task_id}`
- [x] `POST /routing/decide`
- [x] `POST /memory/lookup`
- [x] `GET /context/{task_id}`
- [x] `GET /analyst/digest/{task_id}`

## Deterministic local workflow

- [x] `scripts/demo_local_flow.sh` executes end-to-end
- [x] Sample payloads exist in `scripts/payloads/`
- [x] Baton retrieval works by task id
- [x] Digest reflects persisted events

## UI/developer visibility

- [x] Local console page loads at `http://localhost:3000`
- [x] Console can create and load tasks
- [x] Console shows routing, memory lookup, context bundle, and digest

## Quality gates

- [x] Formatting passes (`make format`)
- [x] Validation suite passes (`make check`)
- [x] Bootstrap succeeds (`bash scripts/bootstrap.sh`)
- [x] Demo flow succeeds (`make demo-local`)

## Operability

- [x] Troubleshooting guide exists (`docs/TROUBLESHOOTING.md`)
- [x] Diagnostics endpoint exists (`GET /diagnostics/task/{task_id}`)
- [x] Status log updated (`docs/STATUS.md`)

## Environment hygiene

- [x] `.env.example` contains no provider/API secrets
- [x] Sensitive values are documented as local-only `.env` entries
