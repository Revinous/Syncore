# Documentation Map

This documentation is organized as a product manual. Start with the path that matches your goal, then use the reference sections when you need exact payloads, commands, or troubleshooting details.

## If you are brand new

Read in this order:

1. [What Is Syncore](what-is-syncore.md)
2. [Core Concepts](concepts.md)
3. [Getting Started](../getting-started.md)
4. [Tutorial 1: First Project](../tutorials/tutorial-1-first-project.md)

This path explains the vocabulary first, then gets you to a running local system and a complete task/run flow.

## If you are setting up an environment

Read:

1. [Native Mode](../environments/native.md)
2. [Docker Mode](../environments/docker.md)
3. [Environment Variables](../environments/env-vars.md)
4. [Configuration Reference](../reference/config-reference.md)

Native mode is for solo development. Docker mode is for a service topology closer to enterprise deployment.

## If you are using Syncore day to day

Read:

1. [CLI Guide](../interfaces/cli.md)
2. [TUI Guide](../interfaces/tui.md)
3. [Web UI Guide](../interfaces/webui.md)
4. [Common Recipes](../recipes/common-recipes.md)

The CLI is best for repeatable commands, the TUI is best for local interactive sessions, and the Web UI is best for visibility.

## If you are integrating with the API

Read:

1. [API Reference](../reference/api.md)
2. [HTTP Examples](../reference/http-examples.md)
3. [Data Contracts](../reference/data-contracts.md)
4. [Error Reference](../reference/error-reference.md)

The API is the system of record. All first-class interfaces should call the API rather than writing directly to SQLite or Postgres.

## If you are operating or debugging Syncore

Read:

1. [Local Development Runbook](../operations/local-development-runbook.md)
2. [Observability and Metrics](../operations/observability-and-metrics.md)
3. [Testing and Quality](../operations/testing-and-quality.md)
4. [Troubleshooting](../operations/troubleshooting.md)

Use these pages when a local workflow fails, a route behaves unexpectedly, or you need to verify a release candidate.

## If you are changing Syncore internals

Read:

1. [System Architecture](../architecture/system-architecture.md)
2. [Data Model](../architecture/data-model.md)
3. [Backend Services](../internals/backend-services.md)
4. [Context Optimizer Internals](../internals/context-optimizer-internals.md)
5. [Autonomy Policy Internals](../internals/autonomy-policy-internals.md)

These sections describe where behavior lives and which layer owns which responsibility.
