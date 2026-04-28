# Deployment Modes

## Native Mode

Use for local developer workflows.

Primary traits:
- SQLite default
- optional Redis
- rapid iteration

## Docker Mode

Use for enterprise-like local stacks.

Primary traits:
- containerized services
- Postgres + Redis defaults
- topology closer to production deployment patterns

## Validation Commands

Native:
- `make bootstrap-local`
- `make dev-local`
- `make local-test`

Docker:
- `make bootstrap`
- `make check`
