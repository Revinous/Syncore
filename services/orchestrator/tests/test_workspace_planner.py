from app.services.workspace_planner import WorkspacePlanner


def test_parse_worker_actions_accepts_plain_json() -> None:
    planner = WorkspacePlanner()
    actions = planner.parse_worker_actions(
        '{"actions":[{"type":"create_file","path":"app.py","content":"print(1)"}]}'
    )
    assert actions == [{"type": "create_file", "path": "app.py", "content": "print(1)"}]


def test_parse_worker_actions_extracts_json_from_wrapped_text() -> None:
    planner = WorkspacePlanner()
    output = """
I will create the first file now.

```json
{"actions":[{"type":"create_file","path":"budget_cli/cli.py","content":"print('hi')"}]}
```
"""
    actions = planner.parse_worker_actions(output)
    assert actions
    assert actions[0]["type"] == "create_file"
    assert actions[0]["path"] == "budget_cli/cli.py"


def test_worker_repair_prompt_explicitly_forbids_tool_unavailable_language() -> None:
    planner = WorkspacePlanner()
    prompt = planner.build_worker_repair_prompt(
        prior_output="I do not have workspace file or command execution tools available."
    )
    assert "Do not mention tools or limitations." in prompt
    assert '{"actions":[' in prompt
