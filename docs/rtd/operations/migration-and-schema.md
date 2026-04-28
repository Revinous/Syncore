# Migration and Schema Operations

## Schema sources

- baseline SQL init scripts for local bootstrap
- Alembic migration path for lifecycle management

## Core commands

```bash
make db-local-init
make db-migrate
make db-revision m="add_new_table"
```

## Native vs Docker notes

- Native mode commonly uses SQLite with local init script.
- Docker mode commonly applies migrations against Postgres service.

## Recommended practice

- generate revision on schema change
- run migrations in CI/local checks
- document upgrade steps in release notes
