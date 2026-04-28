# Getting Started

This chapter gets you to a working Syncore environment with verification at each step.

## Prerequisites

- Linux/macOS/WSL terminal
- `python3` 3.11+
- `node` 20+
- `npm`
- `uv`
- `docker` + `docker compose` (Docker mode only)

## Quick Decision Matrix

- Choose **Native mode** if you want fastest local iteration and minimal dependencies.
- Choose **Docker mode** if you want production-like topology with containerized services.

## Native Mode First Boot

1. Clone and enter repo.
2. Copy env template.
3. Bootstrap local dependencies and sqlite schema.
4. Start local dev services.
5. Verify health and open web UI.

```bash
git clone <repo-url> Syncore
cd Syncore
cp .env.example .env
make bootstrap-local
make dev-local
```

Validation:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/health/services
```

Open:
- `http://localhost:3000`

## Docker Mode First Boot

```bash
cp .env.example .env
make bootstrap
```

Validation:

```bash
docker compose ps
curl http://localhost:8000/health
curl http://localhost:8000/health/services
```

## CLI/TUI First Boot

Install CLI package:

```bash
make install-cli
```

Run:

```bash
syncore status
syncore dashboard
syncore workspace add ./ --name syncore
syncore open syncore
```

## First End-to-End Flow

1. Add workspace.
2. Scan workspace.
3. Create task.
4. Start run.
5. Emit event.
6. Route next action.
7. Generate digest.

CLI skeleton:

```bash
syncore workspace add ./my-repo --name my-repo
syncore workspace scan my-repo
syncore task create "Implement health endpoint" --workspace my-repo
syncore task list
syncore run start <TASK_ID> --agent-role backend
syncore route <TASK_ID>
syncore digest <TASK_ID>
```

## If Something Fails

- Check `syncore status`.
- Check `syncore diagnostics`.
- Read [Troubleshooting](operations/troubleshooting.md).
