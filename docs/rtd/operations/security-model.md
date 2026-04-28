# Security Model (Current Scope)

## API Security

Optional API key enforcement and request rate limiting are supported by config.

## Workspace File Safety

Default protections include:
- path traversal prevention
- secret-like file blocking
- max file size threshold
- forbidden directory exclusions

## Current Boundaries

This phase does not include enterprise IAM/SSO/RBAC. Those are future hardening tracks.
