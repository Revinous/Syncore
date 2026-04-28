# Core Concepts

This page defines the vocabulary used throughout Syncore. Read it once before following the tutorials; it will make the rest of the manual easier to navigate.

## Workspace

A workspace is Syncore’s attachment to a real local project or repository.

It stores:

- `id`: unique workspace identifier
- `name`: human-friendly name used by CLI/TUI
- `root_path`: local filesystem root
- `repo_url`: optional source repository URL
- `branch`: optional branch name
- `runtime_mode`: `native`, `docker`, or `unknown`
- `metadata`: scanner output and other structured information

The workspace root is a safety boundary. Syncore resolves file paths with `pathlib`, blocks path traversal, hides secret-like files, and only exposes relative paths from workspace APIs.

## Workspace Scan

A scan walks the workspace root and extracts useful project metadata.

It detects:

- languages
- frameworks
- package managers
- likely test commands
- entrypoints
- docs
- important files

It skips generated or high-noise directories such as `.git`, `node_modules`, `.venv`, `dist`, `build`, `.next`, `__pycache__`, `target`, and `vendor`.

## Task

A task is a unit of work. It describes what should happen, which workspace it belongs to, and how complex it is.

Core task states:

- `new`
- `in_progress`
- `blocked`
- `completed`

Core task types:

- `analysis`
- `implementation`
- `integration`
- `review`
- `memory_retrieval`
- `memory_update`

Complexity values:

- `low`
- `medium`
- `high`

Task creation does not automatically mean execution. That separation lets Syncore support review gates, queued runs, provider selection, autonomy settings, and manual operator control.

## Agent Run

An agent run is an execution attempt attached to a task.

Supported roles:

- `planner`
- `coder`
- `reviewer`
- `analyst`
- `memory`

Supported run states:

- `queued`
- `running`
- `blocked`
- `completed`
- `failed`

Creating an agent-run record is different from provider-backed execution through `/runs/execute`. The record describes work state; execution calls a run provider and can produce output text, token estimates, context bundle IDs, references, and warnings.

## Project Event

A project event is a timestamped fact in the task timeline.

Events are useful because they give Syncore a durable history independent of any one chat session. Digests, diagnostics, and future context assembly depend on this timeline.

Example event types:

- `analysis.started`
- `plan.drafted`
- `implementation.completed`
- `tests.completed`
- `model.switch.completed`

## Baton Packet

A baton packet is a structured handoff between roles or stages.

It contains:

- objective
- completed work
- constraints
- open questions
- next best action
- relevant artifacts

Batons are important because they preserve handoff intent in a machine-readable shape. They are also treated as high-value context during context assembly.

## Routing Decision

A routing decision recommends which worker role and model tier should handle the next action.

Routing considers:

- task type
- complexity
- whether memory is required

Routing does not execute work by itself. It gives the orchestrator or operator a decision payload.

## Context Bundle

A context bundle is the information prepared for a model or worker.

Raw context can include:

- task state
- latest baton
- recent events
- routing data
- memory lookup results

Optimized context preserves important constraints while reducing low-value bulk. Large logs, files, and tool outputs can be replaced by references that point back to the original full content.

## Context Reference

A context reference stores the original content that was removed or compressed during optimization.

It includes:

- `ref_id`
- task ID
- content type
- original content
- summary
- retrieval hint
- created timestamp

References let Syncore save tokens without destroying access to source material.

## Analyst Digest

An analyst digest is a structured summary of task history and risk.

It includes:

- headline
- summary
- highlights
- event breakdown
- risk level
- total event count

Use digests when you need a quick executive view of what happened.

## Autonomy Cycle

An autonomy cycle is a bounded automatic progression through task stages such as planning, execution, review, retry, and replan.

Autonomy is controlled by settings:

- max retries
- max cycles
- max total steps
- quality thresholds
- review pass requirement

Autonomy is a mode of operation, not a replacement for observability. It should leave enough durable state for a human operator to audit what happened.

## Provider

A provider is an execution backend for model calls.

Examples:

- `local_echo`
- `openai`
- `anthropic`
- `gemini`

`local_echo` is useful for testing the orchestration path without external model calls. External providers require configuration and access.

## One Sentence Mental Model

Syncore turns software work into durable, inspectable workflow state: workspace, task, run, event, baton, context, route, digest, and optional autonomy.
