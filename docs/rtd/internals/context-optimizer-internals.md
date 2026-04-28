# Context Optimizer Internals

## Input composition

Assembler builds raw context from:
- task
- latest baton packet
- recent project events
- routing context if available
- memory lookup results

## Optimization policy behavior (v1)

- preserve critical sections verbatim
- prioritize latest baton fidelity
- summarize older events
- replace oversized logs/tool content with references
- keep estimated token usage within budget thresholds

## Persistence model

- optimized bundles are persisted
- full original heavy payloads are persisted in references
- retrieval by `ref_id` supports later full-fidelity replay

## Why internal (not proxy)

This keeps behavior deterministic, easier to debug locally, and aligned with orchestrator-owned task state.
