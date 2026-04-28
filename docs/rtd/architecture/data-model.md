# Data Model

## Primary Operational Tables

- `workspaces`
- `tasks`
- `agent_runs`
- `project_events`
- `baton_packets`
- `context_bundles`
- `context_references`

## Context Tables

### `context_references`

Purpose:
- Store original heavy content and a retrieval surface when optimized bundles include references instead of full text.

Core fields:
- `ref_id`
- `task_id`
- `content_type`
- `original_content`
- `summary`
- `retrieval_hint`
- `created_at`

### `context_bundles`

Purpose:
- Persist optimized bundle metadata for replay/inspection.

Core fields:
- `bundle_id`
- `task_id`
- `target_agent`
- `target_model`
- `token_budget`
- `optimized_context`
- `included_refs`
- `created_at`

## Backend Differences

- PostgreSQL uses native JSON/JSONB types and UUID semantics.
- SQLite uses text-backed JSON storage and text identifiers where relevant.

The store layer normalizes interface behavior so route/service code can remain backend-agnostic.
