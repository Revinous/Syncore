# Autonomy Workflow

## Endpoints

- `POST /autonomy/scan-once`
- `POST /autonomy/tasks/{task_id}/run`
- `POST /autonomy/tasks/{task_id}/approve`
- `POST /autonomy/tasks/{task_id}/reject`

## Operating Model

Autonomy executes bounded stage loops with policy evaluation at each cycle.

When SDLC enforcement is active (`task.preferences.sdlc_enforce=true`, or tasks in the `syncore` workspace), plan/review quality gates require explicit SDLC checklist coverage:

- requirements
- design
- implementation
- tests
- docs
- release

Review output must show checklist completion with concrete evidence before the cycle can finalize.

## Recommended Rollout

1. enable in native mode only
2. run with conservative retry/cycle limits
3. inspect stage outcomes and quality evaluations
4. tighten/expand policy based on observed performance

## Safety

Autonomy should remain bounded by explicit limits and should produce inspectable stage snapshots for audit and recovery.
