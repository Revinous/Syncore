# Documentation Map

The Syncore documentation is written as a manual, not as a collection of disconnected notes. Use this page to choose the shortest path through the material for the work you are trying to do.

## Start Here

If this is your first time using Syncore, read these pages in order:

1. [What Is Syncore](what-is-syncore.md)
2. [Core Concepts](concepts.md)
3. [Getting Started](../getting-started.md)
4. [Tutorial 1: First Project](../tutorials/tutorial-1-first-project.md)

That path gives you the product model, vocabulary, setup steps, and one complete working flow.

## Choose a Runtime Mode

Syncore has two first-class runtime modes.

| Goal | Use | Read |
| --- | --- | --- |
| Fast solo development without containers | Native mode with SQLite | [Native Mode](../environments/native.md) |
| Service topology with Postgres and Redis | Docker mode | [Docker Mode](../environments/docker.md) |
| Understand every environment setting | Config reference | [Configuration Reference](../reference/config-reference.md) |

Native mode is the normal path for a developer working locally. Docker mode is the normal path when you want the enterprise/local-stack shape.

## Choose an Interface

All interfaces talk to the same FastAPI orchestrator API.

| Interface | Best For | Read |
| --- | --- | --- |
| CLI | Repeatable commands, scripts, quick checks | [CLI Guide](../interfaces/cli.md) |
| TUI | Interactive local work sessions | [TUI Guide](../interfaces/tui.md) |
| Web UI | Dashboards, visibility, team/operator workflows | [Web UI Guide](../interfaces/webui.md) |
| HTTP API | Integrations and exact request control | [API Reference](../reference/api.md) |

The API is the source of truth. The CLI, TUI, and Web UI should not mutate SQLite or Postgres directly.

## Learn by Workflow

Use these chapters when you already understand the basics and want to operate a specific lifecycle.

| Workflow | What It Covers |
| --- | --- |
| [Workspace Lifecycle](../workflows/workspaces.md) | Registering, scanning, and safely listing a local repo |
| [Task and Run Lifecycle](../workflows/tasks-runs.md) | Creating work, starting runs, and reading results |
| [Context Optimization](../workflows/context-optimization.md) | Assembling model context, references, and token metrics |
| [Autonomy](../workflows/autonomy.md) | Staged automatic execution, review, retry, and replan behavior |

## Use Tutorials for Concrete Practice

Tutorials are complete guided flows. They assume you can run Syncore locally.

| Tutorial | Use It When |
| --- | --- |
| [First Project](../tutorials/tutorial-1-first-project.md) | You want to register a repo and run the first task flow |
| [Model Selection and Switching](../tutorials/tutorial-2-model-selection-and-switching.md) | You want to authenticate a provider and switch task model preferences |
| [Context Efficiency](../tutorials/tutorial-3-context-efficiency.md) | You want to measure token savings and context optimization behavior |
| [Build a Small App](../tutorials/tutorial-4-build-small-app-with-syncore.md) | You want to use Syncore to manage a small app build |

## Use Reference When You Need Exactness

Reference pages are deliberately dense and specific.

| Reference | What It Contains |
| --- | --- |
| [API Reference](../reference/api.md) | Endpoint inventory and route groups |
| [HTTP Examples](../reference/http-examples.md) | Copy-pasteable requests for common API flows |
| [CLI Command Reference](../reference/cli-reference.md) | Command inventory |
| [TUI Hotkeys](../reference/tui-hotkeys.md) | Interactive keybinding list |
| [Data Contracts](../reference/data-contracts.md) | Core object shapes and semantics |
| [Error Reference](../reference/error-reference.md) | Common failures and recovery steps |

## Operate and Debug

Use these pages when something is running, failing, or being prepared for release.

| Operations Page | Use It For |
| --- | --- |
| [Local Development Runbook](../operations/local-development-runbook.md) | Daily developer startup, reset, and validation |
| [Observability and Metrics](../operations/observability-and-metrics.md) | Health, SLO, and context efficiency signals |
| [Testing and Quality](../operations/testing-and-quality.md) | Local quality gates before changes are pushed |
| [Troubleshooting](../operations/troubleshooting.md) | Diagnosing broken setup, routes, services, and docs |
| [Security Model](../operations/security-model.md) | Current API and workspace safety boundaries |

## Change Syncore Itself

If you are editing Syncore internals, read these before making broad changes:

1. [System Architecture](../architecture/system-architecture.md)
2. [Data Model](../architecture/data-model.md)
3. [Backend Services](../internals/backend-services.md)
4. [Context Optimizer Internals](../internals/context-optimizer-internals.md)
5. [Autonomy Policy Internals](../internals/autonomy-policy-internals.md)

Those pages explain ownership boundaries and reduce the chance of adding duplicate behavior in the wrong layer.
