# What Is Syncore

Syncore is a local-first orchestration platform for structured software work. It coordinates the state around work: which project is being worked on, what task is active, which agent role is responsible, what happened, what context should be sent to a model, and what the next action should be.

Syncore is not just a chat UI and it is not a model proxy. It is a workflow system with durable state.

## The Problem Syncore Solves

Modern AI-assisted software work often fails for operational reasons:

- context gets copied between tools manually
- task history is scattered across chat logs, terminal output, and memory
- agents lose track of constraints after handoff
- large logs and files are sent repeatedly to models
- there is no durable record of what happened or why
- local solo workflows and enterprise dashboards drift apart

Syncore addresses those problems by making the orchestration layer explicit.

## The Core Idea

Everything flows through one orchestrator API.

```text
CLI / TUI / Web UI
        |
        v
FastAPI Orchestrator
        |
        v
SQLite or Postgres state
```

The interfaces are different ways to operate the same system. They do not own separate state and they should not bypass the API.

## What Syncore Tracks

Syncore tracks operational objects:

- workspaces: safe links to local project roots
- tasks: units of work
- agent runs: execution attempts for roles
- project events: durable timeline entries
- baton packets: structured handoffs
- routing decisions: recommended next action
- context bundles: assembled and optimized model input
- context references: retrievable full content for compressed material
- analyst digests: summaries of task/project state
- autonomy state: staged automatic execution and review state

The goal is continuity. A second worker, interface, or operator should be able to inspect state and understand what happened.

## What Syncore Does

Syncore provides:

- a native local mode using SQLite
- a Docker mode using Postgres and Redis
- a FastAPI backend as the source of truth
- a Web UI for dashboards and operations
- a CLI for repeatable workflows
- a TUI for interactive terminal sessions
- workspace scanning with file safety boundaries
- context optimization and reference retrieval
- metrics for context efficiency and service health
- optional autonomy loops with quality gates

## What Syncore Does Not Do

Syncore does not guarantee a finished production app from a vague prompt. Good output still requires clear task definition, tests, review, provider configuration, and operator judgment.

Syncore also does not currently try to be:

- an LLM proxy server
- a vector database
- a cloud deployment platform
- a replacement for Git
- a replacement for CI
- a secret manager
- a full enterprise IAM/RBAC system

Those boundaries matter because Syncore’s job is orchestration: state, handoff, context, and control.

## Runtime Modes

Native mode:

- runs directly on your machine
- uses SQLite by default
- skips Redis unless required
- is optimized for solo developer workflows

Docker mode:

- runs through Docker Compose
- uses Postgres and Redis
- is closer to enterprise service topology
- is better for validating containerized behavior

Both modes expose the same orchestrator API.

## Control Surfaces

The three primary control surfaces are:

- Web UI: browser dashboard and operator control panel
- CLI: command-first workflows and automation
- TUI: local interactive terminal interface

Use the Web UI when you need visibility. Use the CLI when you know the command. Use the TUI when you want to stay inside a local terminal session.

## A Typical Syncore Flow

1. Register a workspace for a local repo.
2. Scan the workspace to understand its stack and files.
3. Create a task tied to the workspace.
4. Start or execute an agent run.
5. Record project events and baton handoffs.
6. Assemble optimized context for the next worker/model.
7. Route the next action.
8. Generate an analyst digest.
9. Review results through CLI, TUI, Web UI, or API.

Each step is durable. The workflow can be inspected later instead of living only in one model conversation.

## Why This Architecture Matters

Syncore is designed for local work that can mature into enterprise workflows. The same API supports a solo developer opening `syncore my-repo` and an operator viewing dashboards in the browser. That shared backend prevents the two experiences from becoming separate products.
