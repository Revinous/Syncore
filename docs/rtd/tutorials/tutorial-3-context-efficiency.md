# Tutorial 3: Context Efficiency and Token Savings

This tutorial shows how to collect and interpret context efficiency metrics.

## Step 1: Enable layering in `.env`

```env
CONTEXT_LAYERING_ENABLED=true
CONTEXT_LAYERING_DUAL_MODE=true
```

Restart API after changes.

## Step 2: Generate activity

Run normal workflows (task/run/context assemble) so context bundles are created.

## Step 3: Inspect metrics

```bash
syncore metrics context
syncore metrics context --json
syncore metrics layering
```

## How savings are estimated

Syncore compares:
- estimated raw tokens before optimization
- estimated optimized tokens after optimization

Savings are computed from these internal estimates. In dual mode, legacy vs layered comparisons are tracked for rollout analysis.

## Interpreting output

Key fields:
- `bundle_count`
- `raw_tokens`
- `optimized_tokens`
- `saved_tokens`
- `savings_pct`
- `cost_saved_usd` (if configured)

## Caveat

These are estimate-based operational metrics, not billing-authoritative provider invoice values.
