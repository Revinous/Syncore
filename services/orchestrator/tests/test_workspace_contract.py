from __future__ import annotations

from app.services.workspace_contract import load_workspace_contract, normalize_workspace_contract


def test_normalize_workspace_contract_uses_verification_commands() -> None:
    contract = normalize_workspace_contract(
        {
            "verification": {
                "commands": ["python3 -m pytest -q"],
            }
        }
    )

    assert contract["commands"]["test"] == ["python3 -m pytest -q"]
    assert contract["acceptance"]["must_pass_commands"] == ["python3 -m pytest -q"]


def test_load_workspace_contract_accepts_json_payload(tmp_path) -> None:
    (tmp_path / "syncore.yaml").write_text(
        '{"runtime_mode":"native","verification":{"commands":["python3 -m pytest -q"]}}',
        encoding="utf-8",
    )

    contract = load_workspace_contract(tmp_path)

    assert contract["commands"]["test"] == ["python3 -m pytest -q"]
    assert contract["acceptance"]["must_pass_commands"] == ["python3 -m pytest -q"]
