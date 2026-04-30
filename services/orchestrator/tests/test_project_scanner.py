from __future__ import annotations

import json

from app.services.project_scanner import scan_project


def test_scanner_detects_stack_and_docs(tmp_path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    (workspace / "README.md").write_text("# Demo", encoding="utf-8")
    (workspace / "requirements.txt").write_text("fastapi\npytest\n", encoding="utf-8")
    (workspace / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"next": "16.2.4", "react": "19.0.0"},
                "scripts": {"test": "vitest"},
            }
        ),
        encoding="utf-8",
    )

    result = scan_project(workspace)

    assert "python" in result["languages"]
    assert "nextjs" in result["frameworks"]
    assert "react" in result["frameworks"]
    assert "npm" in result["package_managers"]
    assert "pip" in result["package_managers"]
    assert "pytest" in result["test_commands"]
    assert "README.md" in result["docs"]
    assert "package.json" in result["important_files"]
    assert "requirements.txt" in result["important_files"]
    assert "runbook_commands" in result
    assert any("pytest" in item for item in result["runbook_commands"])
