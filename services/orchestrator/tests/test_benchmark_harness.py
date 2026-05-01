from __future__ import annotations

from pathlib import Path

import pytest

from app.services.policy_packs import infer_policy_pack
from app.services.project_scanner import scan_project
from app.services.workspace_contract import load_workspace_contract
from app.services.workspace_readiness import compute_workspace_readiness
from app.services.workspace_runners import select_workspace_runner

BENCHMARK_CASES = [
    {
        "name": "fastapi_service",
        "files": {
            "pyproject.toml": "[project]\nname='svc'\n[tool.pytest.ini_options]\n",
            "app/main.py": "from fastapi import FastAPI\napp = FastAPI()\n",
            "tests/test_main.py": "def test_ok():\n    assert True\n",
            "syncore.yaml": "\n".join(
                [
                    "schema_version: 2",
                    "policy_pack: python-fastapi",
                    "runner: python-fastapi",
                    "environment:",
                    "  required_binaries:",
                    "    - python",
                    "commands:",
                    "  test:",
                    "    - pytest -q",
                    "capabilities:",
                    "  allowed_commands:",
                    "    - pytest -q",
                    "  forbidden_paths:",
                    "    - secrets/",
                    "acceptance:",
                    "  must_pass_commands:",
                    "    - pytest",
                ]
            ),
        },
        "expected_pack": "python-fastapi",
        "expected_runner": "python-fastapi",
        "min_readiness": 60,
    },
    {
        "name": "next_dashboard",
        "files": {
            "package.json": (
                '{"dependencies":{"next":"16.2.4","react":"19.0.0"},'
                '"scripts":{"test":"vitest","build":"next build","lint":"tsc --noEmit"}}'
            ),
            "pages/index.tsx": "export default function Page(){return <div>ok</div>}\n",
            "syncore.yaml": "\n".join(
                [
                    "schema_version: 2",
                    "policy_pack: node-next",
                    "runner: node-next",
                    "environment:",
                    "  required_binaries:",
                    "    - node",
                    "    - npm",
                    "commands:",
                    "  test:",
                    "    - npm test",
                    "  build:",
                    "    - npm run build",
                    "capabilities:",
                    "  allowed_commands:",
                    "    - npm test",
                    "    - npm run build",
                    "acceptance:",
                    "  must_pass_commands:",
                    "    - npm test",
                    "    - npm run build",
                ]
            ),
        },
        "expected_pack": "node-next",
        "expected_runner": "node-next",
        "min_readiness": 65,
    },
    {
        "name": "pnpm_monorepo",
        "files": {
            "pnpm-workspace.yaml": "packages:\n  - apps/*\n  - packages/*\n",
            "nx.json": "{}\n",
            "package.json": (
                '{"dependencies":{"react":"19.0.0"},'
                '"scripts":{"test":"vitest","build":"turbo build","lint":"turbo lint"}}'
            ),
            "apps/web/package.json": '{"name":"web"}\n',
            "packages/ui/package.json": '{"name":"ui"}\n',
            "syncore.yaml": "\n".join(
                [
                    "schema_version: 2",
                    "policy_pack: monorepo-pnpm",
                    "runner: monorepo-pnpm",
                    "environment:",
                    "  required_binaries:",
                    "    - node",
                    "    - pnpm",
                    "commands:",
                    "  test:",
                    "    - pnpm test",
                    "  build:",
                    "    - pnpm build",
                    "capabilities:",
                    "  allowed_commands:",
                    "    - pnpm test",
                    "    - pnpm build",
                    "acceptance:",
                    "  must_pass_commands:",
                    "    - pnpm test",
                ]
            ),
        },
        "expected_pack": "monorepo-pnpm",
        "expected_runner": "monorepo-pnpm",
        "min_readiness": 55,
    },
]


@pytest.mark.parametrize("case", BENCHMARK_CASES, ids=[case["name"] for case in BENCHMARK_CASES])
def test_benchmark_harness_repo_classes(case: dict[str, object], tmp_path: Path) -> None:
    files = case["files"]
    assert isinstance(files, dict)
    for rel, content in files.items():
        target = tmp_path / str(rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(content), encoding="utf-8")

    scan = scan_project(tmp_path)
    pack = infer_policy_pack(scan)
    contract = load_workspace_contract(tmp_path)
    runner = select_workspace_runner(policy_pack=pack, scan=scan, contract=contract)
    readiness = compute_workspace_readiness(
        scan=scan,
        contract=contract,
        runner=runner,
        learning={},
    )

    assert pack == case["expected_pack"]
    assert runner["name"] == case["expected_runner"]
    assert readiness["score"] >= int(case["min_readiness"])
