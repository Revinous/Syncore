# Context Optimization Layer

Syncore implements an internal context optimization layer inside orchestrator services. It is not a proxy server.

## Goals

- Assemble relevant context from task state, baton history, events, memory, and routing context.
- Preserve critical constraints verbatim.
- Compress low-value historical bulk.
- Offload heavy logs/tool outputs into retrievable references.
- Keep optimized payload near token budget.

## Deterministic Behavior

The current optimizer is deterministic/local-first:
- critical sections are preserved
- recent baton signal is favored
- older events are summarized
- large payloads are truncated and referenced

## Retrieval Path

Referenced content can be fetched later via `ref_id`, enabling full-fidelity recovery when needed without overloading every model call.
