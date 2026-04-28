# Context Optimization Workflow

## Entry Point

`POST /context/assemble`

Inputs:
- task id
- target agent
- target model
- token budget

## Pipeline Behavior

1. Build raw context bundle.
2. Preserve critical directives/constraints.
3. Summarize low-value history.
4. Replace oversized payloads with context references.
5. Persist optimized bundle and references.
6. Return optimized payload and estimated token count.

## Retrieval

`GET /context/references/{ref_id}` returns persisted original content and summary metadata.

## Practical Guidance

- set realistic token budgets per model family
- avoid marking too much content as critical
- use references for repeat logs to maximize reuse
