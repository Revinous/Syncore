from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.config import Settings, get_settings

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


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


@router.get("/latest", response_model=BenchmarkReportResponse)
def get_latest_benchmark_report(
    settings: Settings = Depends(get_settings),
) -> BenchmarkReportResponse:
    report_path = Path(settings.benchmark_report_path)
    if not report_path.exists():
        return BenchmarkReportResponse(available=False)

    payload = json.loads(report_path.read_text(encoding="utf-8"))
    cases: list[BenchmarkCaseResult] = []
    for item in payload.get("cases", []):
        if isinstance(item, dict):
            runner = item.get("readiness_runner")
            if isinstance(runner, dict):
                item = dict(item)
                item["readiness_runner"] = runner.get("name")
        cases.append(BenchmarkCaseResult.model_validate(item))

    baseline_pass_count = sum(1 for case in cases if case.baseline_test_passed)
    live_pass_count = sum(1 for case in cases if case.live_execution_passed)
    meaningful_change_count = sum(1 for case in cases if case.meaningful_change)

    return BenchmarkReportResponse(
        available=True,
        generated_at=payload.get("generated_at"),
        api_url=payload.get("api_url"),
        execute_enabled=bool(payload.get("execute_enabled", False)),
        provider=payload.get("provider"),
        model=payload.get("model"),
        case_count=len(cases),
        baseline_pass_count=baseline_pass_count,
        live_pass_count=live_pass_count,
        meaningful_change_count=meaningful_change_count,
        cases=cases,
        raw=payload,
    )
