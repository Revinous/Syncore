# Architecture Standards

This document defines the structural rules for Syncore's codebase.

The goal is not stylistic purity. The goal is to keep the system easy to change, easy to test, and hard to regress into a small number of oversized modules.

## Core Rules

### 1. Routes are adapters, not business logic containers

FastAPI route modules under `services/orchestrator/app/api/routes/` should:
- validate request/response shapes
- obtain dependencies
- call services
- translate service failures into HTTP failures when needed

Route modules should not:
- assemble report payloads from files
- perform direct JSON file parsing for domain results
- implement policy selection logic
- contain large orchestration branches

Exception:
- operational probes may inspect local filesystem state when that inspection is itself the health check being reported

### 2. Services must have a primary reason to change

A service may coordinate multiple collaborators, but it should still have one primary concern.

Good examples:
- execution policy resolution
- workspace verification
- benchmark report retrieval
- autonomy candidate handling
- autonomy finalization

Bad examples:
- one service that routes models, edits files, runs commands, computes learning metadata, writes reports, and decides retry policy

### 3. CLI entrypoints stay thin

`apps/cli/syncore_cli/main.py` should be wiring, public command registration, and stable test seams only.

Domain logic belongs in:
- `apps/cli/syncore_cli/commands/`
- `apps/cli/syncore_cli/dependencies.py`
- `apps/cli/syncore_cli/presentation.py`
- `apps/cli/syncore_cli/workspace_resolution.py`
- `apps/cli/syncore_cli/local_runtime.py`

### 4. Operator pages are compositional

Page modules in `apps/web/pages/` should primarily:
- read route params
- call hooks
- compose panels
- handle page-shell level loading/error framing

Page modules should not become mini-apps that own all fetch logic, mutations, and presentation branches inline.

Hooks belong in `apps/web/src/hooks/`.
Focused rendering belongs in `apps/web/src/components/`.

### 5. Architectural ratchet

Some legacy modules are still larger than the target standard. The current rule is a ratchet:
- do not add new oversized modules
- do not let existing oversized modules grow beyond their recorded baseline
- extract new concerns into focused modules instead of adding more branches to the largest files

## Size Guardrails

These are engineering guardrails, not aesthetic goals.

### Hard guardrails for new files

- Python route modules: `<= 250` lines
- Python service modules: `<= 400` lines unless explicitly allowlisted
- CLI entry modules: `<= 250` lines
- Web page modules: `<= 250` lines unless they are transitional and scheduled for decomposition

### Ratchet guardrails for known large modules

The following files are currently above ideal size and are on a reduction path:
- `services/orchestrator/app/services/autonomy_service.py`
- `services/orchestrator/app/services/run_execution_service.py`
- `apps/cli/syncore_cli/tui.py`
- `services/orchestrator/app/services/task_service.py`

They must not grow beyond the recorded baseline in `scripts/structural_guardrails.py`.

## Layering Rules

### Backend

- routes depend on services
- services may depend on storage protocols, contracts, and focused helpers
- services should not depend on route modules
- route-local file I/O for domain report assembly is disallowed

### CLI

- commands depend on API client, runtime helpers, and presentation helpers
- `main.py` should not re-absorb domain command logic

### Web

- pages depend on hooks and components
- hooks depend on API client/types
- components should be presentational or narrowly interactive

## Testing Expectations

Any structural refactor must preserve:
- `make check`
- CLI tests
- web smoke/typecheck/build
- relevant backend domain tests

When extracting a service boundary, add or keep focused tests for the extracted unit where practical.

## Contributor Guidance

Before adding logic:
1. Decide which layer owns it.
2. If a large module already exists, prefer extracting a new focused module instead of adding more branches.
3. If you must exceed a guardrail, document why and update the ratchet intentionally.
4. Do not move logic into adapters for convenience.

## Definition of Done for Architecture Work

A structural change is only complete when:
- the ownership boundary is clearer than before
- public behavior is preserved
- tests pass
- the change does not weaken the ratchet
