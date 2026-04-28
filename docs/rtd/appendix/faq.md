# FAQ

## Why is there one backend for all interfaces?

To keep state semantics consistent and prevent drift between web and terminal workflows.

## Can I use Syncore without Docker?

Yes. Native mode is first-class and defaults to SQLite.

## Does creating a task auto-run it?

Not by default. Task creation and run execution are intentionally separated so operators can control scheduling and model/provider selection.

## Can I switch model after creating a task?

Yes, use task model switch capabilities via CLI/API/TUI where exposed.

## Why are some files hidden in workspace file listings?

Secret-like and unsafe files are blocked by default for safety.
