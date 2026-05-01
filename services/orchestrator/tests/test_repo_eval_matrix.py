from __future__ import annotations

from pathlib import Path

import pytest

from app.services.policy_packs import infer_policy_pack
from app.services.project_scanner import scan_project
from app.services.workspace_contract import (
    build_runbook_from_contract,
    normalize_workspace_contract,
)
from app.services.workspace_runners import select_workspace_runner


@pytest.mark.parametrize(
    ("files", "expected_pack", "expected_runner", "expected_command"),
    [
        (
            {
                "pyproject.toml": "[project]\nname='demo'\n[tool.pytest.ini_options]\n",
                "app.py": "print('hi')\n",
            },
            "python-fastapi",
            "python-fastapi",
            "uv run pytest -q",
        ),
        (
            {
                "manage.py": "print('django')\n",
                "requirements.txt": "django\npytest\n",
            },
            "python-django",
            "python-django",
            "python manage.py test",
        ),
        (
            {
                "package.json": (
                    '{"dependencies":{"next":"16.2.4"},'
                    '"scripts":{"test":"vitest"}}'
                ),
                "src/index.ts": "export {}\n",
            },
            "node-next",
            "node-next",
            "npm test",
        ),
        (
            {
                "package.json": (
                    '{"dependencies":{"express":"5.0.0"},'
                    '"scripts":{"test":"jest"}}'
                ),
            },
            "node-express",
            "node-express",
            "npm test",
        ),
        (
            {
                "pnpm-workspace.yaml": "packages:\n  - apps/*\n",
                "package.json": (
                    '{"dependencies":{"vite":"5.0.0","react":"19.0.0","turbo":"2.0.0"},'
                    '"scripts":{"test":"vitest"}}'
                ),
            },
            "vite-react",
            "vite-react",
            "npm test",
        ),
        (
            {
                "pnpm-workspace.yaml": "packages:\n  - apps/*\n",
                "nx.json": "{}",
                "package.json": (
                    '{"dependencies":{"react":"19.0.0"},'
                    '"scripts":{"test":"vitest"}}'
                ),
            },
            "monorepo-pnpm",
            "monorepo-pnpm",
            "pnpm test",
        ),
        (
            {
                "go.mod": "module demo\n",
                "main.go": "package main\nfunc main() {}\n",
            },
            "go-service",
            "go-service",
            "go test ./...",
        ),
        (
            {
                "Cargo.toml": "[package]\nname='demo'\nversion='0.1.0'\n",
                "src/main.rs": "fn main() {}\n",
            },
            "rust-cli",
            "rust-cli",
            "cargo test",
        ),
        (
            {
                "build.gradle": "plugins { id 'java' }\n",
                "src/main/java/App.java": "class App {}\n",
            },
            "java-gradle",
            "java-gradle",
            "gradle test",
        ),
    ],
)
def test_repo_eval_matrix_infers_pack_runner_and_commands(
    tmp_path: Path,
    files: dict[str, str],
    expected_pack: str,
    expected_runner: str,
    expected_command: str,
) -> None:
    for rel, content in files.items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")

    scan = scan_project(tmp_path)
    pack = infer_policy_pack(scan)
    contract = normalize_workspace_contract({})
    runbook = build_runbook_from_contract(contract)
    runner = select_workspace_runner(policy_pack=pack, scan=scan, contract=contract)

    assert pack == expected_pack
    assert runner["name"] == expected_runner
    commands = list((runner.get("commands") or {}).get("test", []))
    assert expected_command in commands
    assert isinstance(runbook, dict)
