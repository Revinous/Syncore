# Read the Docs Branches and Versions

## Goal

Publish segmented docs per branch and tag so users can switch between stable and in-progress docs.

## Recommended strategy

- `main` branch: latest development docs
- `stable` tag (or release tags): production-ready docs
- feature branches: optional preview builds

## Read the Docs setup

1. Connect repo in Read the Docs.
2. Ensure `.readthedocs.yaml` is in repo root.
3. In RTD project settings:
   - Enable version builds.
   - Activate `main` and release tags.
   - Optionally activate selected feature branches.
4. Set default version to `stable` (or `latest`, based on your release policy).

## Team usage

- Write docs updates in same PR as code changes.
- Keep `docs/rtd/` structure stable.
- Verify docs locally: `mkdocs serve`.
