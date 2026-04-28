# Local Development Runbook

This runbook is for developers working on Syncore itself.

## Daily startup

```bash
cd Syncore
make dev-local
```

In a second terminal:

```bash
syncore status
syncore dashboard
```

## Clean local database

Native SQLite:

```bash
rm -f .syncore/syncore.db
make db-local-init
```

Docker/Postgres:

```bash
docker compose down -v
make bootstrap
```

Use the clean reset only when you intentionally want to discard local task/run/workspace state.

## Verify route registration

```bash
curl http://localhost:8000/diagnostics/routes
```

Expected route groups include:

- health
- dashboard
- workspaces
- tasks
- agent-runs
- project-events
- baton-packets
- routing
- context
- analyst
- diagnostics
- autonomy
- metrics

## Verify schema-dependent features

Run:

```bash
make local-test
```

This uses SQLite settings and exercises orchestrator/memory tests.

## Verify full project health

Run:

```bash
make check
```

This is the broader quality gate and should be used before pushing larger changes.

## Verify docs

```bash
make docs-build
```

The build must create `site/index.html` for Read the Docs root serving.

## Inspect local service logs

When CLI auto-starts the orchestrator, logs are written to:

```text
.syncore/orchestrator-cli.log
```

For Docker:

```bash
make logs
```

## Avoiding environment mixups

Before debugging missing data, print the active mode:

```bash
curl http://localhost:8000/diagnostics/config
```

Common mismatch:

- CLI points at native `localhost:8000`
- Docker stack is running with different database state
- stale native API process is still serving old SQLite data

Stop stale processes or use one runtime mode at a time when validating stateful behavior.
