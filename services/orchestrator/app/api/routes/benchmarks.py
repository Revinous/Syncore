from __future__ import annotations

from fastapi import APIRouter, Depends

from app.config import Settings, get_settings
from app.services.benchmark_report_service import (
    BenchmarkReportResponse,
    BenchmarkReportService,
)

router = APIRouter(prefix="/benchmarks", tags=["benchmarks"])


def get_benchmark_report_service(
    settings: Settings = Depends(get_settings),
) -> BenchmarkReportService:
    return BenchmarkReportService(settings.benchmark_report_path)


@router.get("/latest", response_model=BenchmarkReportResponse)
def get_latest_benchmark_report(
    service: BenchmarkReportService = Depends(get_benchmark_report_service),
) -> BenchmarkReportResponse:
    return service.get_latest_report()
