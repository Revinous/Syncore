# Tutorial 2: Provider and Model Selection

This tutorial covers selecting providers/models, verifying model access, and switching models per task.

## Step 1: Authenticate provider (OpenAI)

```bash
syncore auth openai login
syncore auth openai status
syncore auth openai models
```

`models` output reflects account-level model availability.

## Step 2: Create task and inspect

```bash
syncore task create "Design API pagination policy" --workspace my-app
syncore task list --workspace my-app
syncore task show <TASK_ID>
```

## Step 3: Switch task model

```bash
syncore task switch-model <TASK_ID> \
  --provider openai \
  --model gpt-5.4 \
  --target-agent coder \
  --token-budget 8000 \
  --reason "Need stronger coding depth"
```

## Step 4: Verify model-switch event trail

```bash
syncore task show <TASK_ID>
syncore events <TASK_ID>
```

Look for `model.switch.completed` event payload.

## Notes

- Model switching updates task execution preference context.
- Runs created before switch may still reference prior configuration depending on orchestration timing.
