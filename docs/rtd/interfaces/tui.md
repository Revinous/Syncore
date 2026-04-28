# TUI Guide

The TUI is the interactive terminal surface for Syncore operations.

## Launch Modes

```bash
syncore tui
```

or scoped session:

```bash
syncore open my-app
syncore my-app
```

## Core Interaction Model

- left pane: workspace/task lists
- center pane: runs/event stream
- right pane: selected detail
- status/header: API/runtime state

## Task Creation Flow

1. trigger new task hotkey
2. choose provider
3. search model list (type-to-filter)
4. choose complexity
5. submit

Task creation does not force run execution by default.

## Typical Operator Loop

1. select workspace
2. create task
3. start run
4. inspect events/baton updates
5. request route decision
6. request digest
7. inspect run result

## Offline/Recovery Behavior

If API is unavailable, TUI should:
- display offline status
- continue running without crash
- recover after refresh once API is back

## Hotkeys

See full map: [TUI Hotkeys](../reference/tui-hotkeys.md)
