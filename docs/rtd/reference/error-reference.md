# Error Reference

This page explains common errors by symptom, likely cause, and the next useful command.

## Connection refused

Example:

```text
Could not reach Syncore API at http://localhost:8000: [Errno 111] Connection refused
```

Meaning:

The orchestrator API is not listening at the configured URL.

Check:

```bash
echo "$SYNCORE_API_URL"
curl http://localhost:8000/health
```

Fix:

```bash
make dev-local
```

or, for Docker:

```bash
make bootstrap
docker compose ps
```

## Workspace not found

Meaning:

The CLI could not resolve the value as a workspace ID, workspace name, or local directory path.

Check:

```bash
syncore workspace list
pwd
ls -la
```

Fix:

```bash
syncore workspace add /absolute/path/to/repo --name my-repo
```

## Path traversal blocked

Meaning:

A workspace file request tried to access a path outside the registered root.

Fix:

Use a relative path inside the workspace root. Do not pass `..` paths or absolute paths through workspace file APIs.

## Access denied to file

Meaning:

The requested file matched a blocked secret pattern or ignored directory.

Blocked examples:

- `.env`
- `.env.local`
- `id_rsa`
- `*.pem`
- `*.key`
- `secrets.*`
- `credentials.*`

Fix:

Do not expose secrets through Syncore workspace file APIs. Use explicit operator-controlled configuration for secrets.

## Task not found

Meaning:

The task ID does not exist in the active database backend.

Check:

```bash
syncore task list
syncore diagnostics
```

Common cause:

You created the task in native SQLite mode but are now pointing the CLI at Docker/Postgres mode, or the reverse.

## Provider not configured

Meaning:

A provider-backed run requested a provider without the required API key/config.

Check:

```bash
syncore providers
syncore auth openai status
```

Fix:

Set the provider key in `.env` for orchestrator execution or use the supported CLI auth flow where applicable.

## Redis degraded in native mode

Meaning:

Redis is unavailable but may not be required.

Check:

```bash
curl http://localhost:8000/health/services
```

If `REDIS_REQUIRED=false`, Redis can be skipped in native mode.

## Docs build has no root index

Meaning:

MkDocs did not generate `site/index.html`.

Fix:

Ensure `docs/index.md` exists and `mkdocs.yml` maps `Home: index.md`.

Validate:

```bash
make docs-build
test -f site/index.html
```
