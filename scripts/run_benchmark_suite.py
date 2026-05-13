#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    repo_url: str
    test_command: str


CASES = [
    BenchmarkCase(
        name="itsdangerous",
        repo_url="https://github.com/pallets/itsdangerous",
        test_command="uv run pytest -q",
    ),
    BenchmarkCase(
        name="click",
        repo_url="https://github.com/pallets/click",
        test_command="uv run pytest -q",
    ),
]


def _request(base_url: str, path: str, method: str = "GET", data: dict[str, Any] | None = None) -> Any:
    body = None if data is None else json.dumps(data).encode("utf-8")
    request = urllib.request.Request(
        urllib.parse.urljoin(base_url, path),
        data=body,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def _ensure_workspace(base_url: str, root_path: str, name: str) -> dict[str, Any]:
    workspaces = _request(base_url, "/workspaces")
    for workspace in workspaces:
        if workspace["root_path"] == root_path:
            return workspace
    return _request(
        base_url,
        "/workspaces",
        "POST",
        {
            "name": name,
            "root_path": root_path,
            "runtime_mode": "native",
            "metadata": {},
        },
    )


def _clone_or_update(case: BenchmarkCase, repo_root: Path) -> Path:
    target = repo_root / case.name
    if target.exists():
        subprocess.run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", "HEAD"], check=True)
        subprocess.run(["git", "-C", str(target), "reset", "--hard", "FETCH_HEAD"], check=True)
    else:
        subprocess.run(["git", "clone", "--depth", "1", case.repo_url, str(target)], check=True)
    return target


def _run_command(command: str, cwd: Path) -> tuple[bool, str]:
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        shell=True,
        capture_output=True,
        text=True,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    excerpt = output.strip()[-4000:]
    return completed.returncode == 0, excerpt


def _build_live_prompt(case: BenchmarkCase) -> str:
    return (
        "Inspect this repository and make one safe, deterministic improvement. "
        "Prefer adding or refining syncore.yaml if no stronger repo-specific fix is obvious. "
        f"Verify the result with `{case.test_command}` and report the outcome clearly."
    )


def _resolve_provider_model() -> tuple[str | None, str | None]:
    openai_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    anthropic_key = (os.getenv("ANTHROPIC_API_KEY") or "").strip()
    gemini_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if openai_key and openai_key != "replace_me":
        return "openai", "gpt-5.4"
    if anthropic_key and anthropic_key != "replace_me":
        return "anthropic", "claude-3-7-sonnet-latest"
    if gemini_key and gemini_key != "replace_me":
        return "gemini", "gemini-2.5-pro"
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Syncore benchmark suite against public repositories.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=".syncore/benchmarks/latest.json")
    parser.add_argument("--repo-dir", default=".syncore/benchmarks/repos")
    parser.add_argument("--limit", type=int, default=len(CASES))
    parser.add_argument("--execute", action="store_true", help="Attempt a live task execution for each case.")
    args = parser.parse_args()

    base_url = args.api_url.rstrip("/")
    repo_dir = Path(args.repo_dir)
    repo_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    provider, model = _resolve_provider_model()
    execute_enabled = bool(args.execute and provider and model)

    report_cases: list[dict[str, Any]] = []

    for case in CASES[: args.limit]:
        case_root = _clone_or_update(case, repo_dir)
        baseline_ok, baseline_output = _run_command(case.test_command, case_root)
        workspace = _ensure_workspace(base_url, str(case_root.resolve()), f"benchmark-{case.name}")
        scan = _request(base_url, f"/workspaces/{workspace['id']}/scan", "POST")
        scanned_workspace = scan.get("workspace", workspace)
        metadata = scanned_workspace.get("metadata", {}) or {}

        runner_value = metadata.get("workspace_runner")
        if isinstance(runner_value, dict):
            runner_value = runner_value.get("name")

        case_result: dict[str, Any] = {
            "name": case.name,
            "repo_url": case.repo_url,
            "root_path": str(case_root.resolve()),
            "baseline_test_command": case.test_command,
            "baseline_test_passed": baseline_ok,
            "workspace_id": scanned_workspace["id"],
            "languages": scan.get("scan", {}).get("languages", []),
            "frameworks": scan.get("scan", {}).get("frameworks", []),
            "package_managers": scan.get("scan", {}).get("package_managers", []),
            "test_commands": scan.get("scan", {}).get("test_commands", []),
            "readiness_pack": metadata.get("policy_pack"),
            "readiness_runner": runner_value,
            "live_execution_attempted": False,
            "live_execution_passed": False,
            "task_id": None,
            "execution_outcome": None,
            "verification_status": None,
            "meaningful_change": None,
            "notes": [],
        }
        if not baseline_ok:
            case_result["notes"].append(f"Baseline test failed: {baseline_output[-300:]}")

        if execute_enabled:
            task = _request(
                base_url,
                "/tasks",
                "POST",
                {
                    "title": f"Benchmark improvement: {case.name}",
                    "task_type": "implementation",
                    "complexity": "medium",
                    "workspace_id": scanned_workspace["id"],
                },
            )
            case_result["task_id"] = task["id"]
            case_result["live_execution_attempted"] = True
            try:
                _request(
                    base_url,
                    "/runs/execute-auto",
                    "POST",
                    {
                        "task_id": task["id"],
                        "stage": "execute",
                        "prompt": _build_live_prompt(case),
                        "target_agent": "coder",
                        "provider": provider,
                        "target_model": model,
                        "agent_role": "coder",
                        "token_budget": 8000,
                    },
                )
                report = _request(base_url, f"/tasks/{task['id']}/execution-report")
                case_result["execution_outcome"] = report.get("outcome_status")
                case_result["verification_status"] = report.get("verification_status")
                case_result["meaningful_change"] = report.get("meaningful_change")
                case_result["live_execution_passed"] = bool(
                    report.get("outcome_status") == "completed"
                    and report.get("verification_status") in {"passed", "completed", "ok"}
                )
            except urllib.error.HTTPError as exc:
                case_result["notes"].append(f"Live execution failed: HTTP {exc.code}")
            except Exception as exc:  # pragma: no cover - defensive scripting
                case_result["notes"].append(f"Live execution failed: {exc}")

        report_cases.append(case_result)

    payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_url": base_url,
        "execute_enabled": execute_enabled,
        "provider": provider,
        "model": model,
        "cases": report_cases,
    }
    output_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
