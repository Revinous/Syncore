# Testing and Quality Gates

## Baseline Commands

- `make test`
- `make check`
- `make local-test`
- `make ui-check`

## Recommended Pre-Release Sequence

1. run backend tests
2. run frontend checks
3. run native mode smoke flow
4. run docker mode smoke flow
5. validate demo workflow end-to-end

## Documentation Checks

- `make docs-build`
- verify RTD version build status
