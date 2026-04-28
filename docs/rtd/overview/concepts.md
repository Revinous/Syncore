# Core Concepts

## Workspace

A workspace is a safe attachment to a local repository path. It gives Syncore a bounded filesystem root for scanning and file listing.

Key fields:
- `id`
- `name`
- `root_path`
- `repo_url`
- `branch`
- `runtime_mode`
- `metadata`
- `created_at`
- `updated_at`

## Task

A task describes a work objective.

Typical fields include:
- title
- description
- status
- workspace association
- complexity
- preferred provider/model

## Agent Run

A run is a concrete execution attempt tied to a task.

Runs have:
- `run_id`
- task linkage
- agent role
- status (`pending`, `running`, `completed`, `failed`, etc.)
- timestamps
- result payload

## Project Event

Events are durable timeline entries for task activity. They serve as the factual record for diagnostics, digests, and historical continuity.

## Baton Packet

A baton packet represents structured handoff state between phases or roles.

## Routing Decision

Routing outputs the next recommended action for a task based on known state.

## Context Bundle

Context assembly and optimization produce an optimized bundle suitable for model execution:
- preserve critical sections
- summarize low-value bulk
- replace heavy content with retrievable references

## Analyst Digest

Digest is a synthesized summary of task/project signal from event history and related records.

## Autonomy Cycle

Autonomy iterates through staged execution with quality checks, potential replans, and persisted cycle snapshots.
