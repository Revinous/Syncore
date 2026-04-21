# AGENTS.md

## Project purpose
Build a vendor-agnostic agent workforce platform where specialized agents act like employees, hand off work through structured baton packets, store durable context outside the prompt, switch models based on task complexity, and produce executive-readable project insight through a separate analyst service.

## Non-negotiable rules
1. Respect the repository structure and phased plan in `docs/IMPLEMENTATION_PLAN.md`.
2. Prefer explicit, simple architecture over clever abstractions.
3. Do not add infrastructure that is not justified by the current phase.
4. Every new service must include a README, typed interfaces, and tests.
5. Never pass giant raw transcripts between agents when a structured handoff packet will do.
6. Durable state belongs in PostgreSQL, not in ad hoc local files.
7. Keep commits small and milestone-based.

## Initial phases
- Phase 1: scaffold monorepo, local containers, database schema, FastAPI orchestrator, basic Next.js shell.
- Phase 2: add memory retrieval, routing logic, and baton packet flow.
- Phase 3: add analyst/event summarization and observability.
- Phase 4: prepare AWS deployment assets.

## Coding standards
- TypeScript and Python must be strongly typed where practical.
- Use pydantic for Python contracts.
- Use clear filenames and predictable module boundaries.
- Add tests for schemas, routing logic, and API health checks.

## Required checks before task completion
- Run formatting.
- Run tests.
- Update `docs/STATUS.md` with what changed.
- If architecture changed, update `docs/DECISIONS.md`.
