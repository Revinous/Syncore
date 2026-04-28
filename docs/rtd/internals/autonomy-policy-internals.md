# Autonomy Policy Internals

## Core control loop

Autonomy runs task stages and checks outputs against quality gates.

## Replan and retry

Policy can:
- retry current stage with bounded backoff
- trigger replan branch when quality/risk thresholds fail

## Snapshotting

Cycle/stage snapshots are persisted for:
- auditability
- recovery
- policy evaluation over time

## Limits

Bounded by env-configured limits to prevent runaway execution:
- retries
- cycles
- total steps
