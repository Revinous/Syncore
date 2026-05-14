from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field


class BenchmarkCaseResult(BaseModel):
    name: str
    repo_url: str
    root_path: str
    baseline_test_command: str
    baseline_test_passed: bool
    workspace_id: str | None = None
    languages: list[str] = Field(default_factory=list)
    frameworks: list[str] = Field(default_factory=list)
    package_managers: list[str] = Field(default_factory=list)
    test_commands: list[str] = Field(default_factory=list)
    readiness_pack: str | None = None
    readiness_runner: str | None = None
    live_execution_attempted: bool = False
    live_execution_passed: bool = False
    task_id: str | None = None
    execution_outcome: str | None = None
    verification_status: str | None = None
    meaningful_change: bool | None = None
    notes: list[str] = Field(default_factory=list)


class BenchmarkReportResponse(BaseModel):
    available: bool
    generated_at: str | None = None
    api_url: str | None = None
    execute_enabled: bool = False
    provider: str | None = None
    model: str | None = None
    case_count: int = 0
    baseline_pass_count: int = 0
    live_pass_count: int = 0
    meaningful_change_count: int = 0
    cases: list[BenchmarkCaseResult] = Field(default_factory=list)
    raw: dict[str, Any] | None = None


class BenchmarkReportService:
    def __init__(self, report_path: str) -> None:
        self._report_path = Path(report_path)

    def get_latest_report(self) -> BenchmarkReportResponse:
        if not self._report_path.exists():
            return BenchmarkReportResponse(available=False)

        payload = json.loads(self._report_path.read_text(encoding="utf-8"))
        cases = [
            BenchmarkCaseResult.model_validate(self._normalize_case_payload(item))
            for item in payload.get("cases", [])
            if isinstance(item, dict)
        ]
        return BenchmarkReportResponse(
            available=True,
            generated_at=payload.get("generated_at"),
            api_url=payload.get("api_url"),
            execute_enabled=bool(payload.get("execute_enabled", False)),
            provider=payload.get("provider"),
            model=payload.get("model"),
            case_count=len(cases),
            baseline_pass_count=sum(1 for case in cases if case.baseline_test_passed),
            live_pass_count=sum(1 for case in cases if case.live_execution_passed),
            meaningful_change_count=sum(1 for case in cases if case.meaningful_change),
            cases=cases,
            raw=payload,
        )

    @staticmethod
    def _normalize_case_payload(item: dict[str, Any]) -> dict[str, Any]:
        runner = item.get("readiness_runner")
        if isinstance(runner, dict):
            normalized = dict(item)
            normalized["readiness_runner"] = runner.get("name")
            return normalized
        return item
