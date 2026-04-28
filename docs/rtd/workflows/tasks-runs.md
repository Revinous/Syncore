# Task and Run Workflow

## Canonical Flow

1. Create task.
2. Start run for role.
3. Append project events.
4. Persist baton handoffs.
5. Query routing decision.
6. Generate digest.
7. Review run result and diagnostics.

## Failure Handling

- run can be canceled or resumed
- diagnostics should be checked for state mismatches
- event trail is primary source for timeline reconstruction
