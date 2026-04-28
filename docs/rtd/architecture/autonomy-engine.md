# Autonomy Engine

Autonomy enables staged task progression with safety controls.

## Stage Pattern

Typical flow:
- plan
- execute
- review
- replan (if needed)

## Quality Gates

Outputs are evaluated before advancing stages. Failed gates can trigger retries or replans based on configured policies.

## Persistence

Cycle snapshots and stage outcomes are persisted to support auditability, observability, and future policy improvement.

## Guardrails

Configurable limits constrain behavior:
- max retries
- max cycles
- max total steps
- review pass requirement
- minimum output thresholds
