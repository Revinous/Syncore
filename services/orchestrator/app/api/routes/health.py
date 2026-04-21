from typing import Literal

import psycopg
import redis
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str
    service: str
    environment: str


class DependencyStatus(BaseModel):
    name: str
    status: Literal["ok", "unavailable"]
    detail: str


class ServiceHealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    environment: str
    dependencies: list[DependencyStatus]


def probe_postgres(postgres_dsn: str) -> tuple[Literal["ok", "unavailable"], str]:
    try:
        with psycopg.connect(postgres_dsn) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return "ok", "reachable"
    except Exception as error:
        return "unavailable", str(error)


def probe_redis(redis_url: str) -> tuple[Literal["ok", "unavailable"], str]:
    try:
        client = redis.Redis.from_url(redis_url)
        if client.ping():
            return "ok", "reachable"
        return "unavailable", "ping failed"
    except Exception as error:
        return "unavailable", str(error)


@router.get("/health", response_model=HealthResponse)
def health_check(settings: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="orchestrator",
        environment=settings.environment,
    )


@router.get("/health/services", response_model=ServiceHealthResponse)
def services_health_check(settings: Settings = Depends(get_settings)) -> ServiceHealthResponse:
    postgres_status, postgres_detail = probe_postgres(settings.postgres_dsn)
    redis_status, redis_detail = probe_redis(settings.redis_url)

    dependencies = [
        DependencyStatus(name="postgres", status=postgres_status, detail=postgres_detail),
        DependencyStatus(name="redis", status=redis_status, detail=redis_detail),
    ]

    overall_status: Literal["ok", "degraded"] = "ok"
    if any(dependency.status != "ok" for dependency in dependencies):
        overall_status = "degraded"

    return ServiceHealthResponse(
        status=overall_status,
        service="orchestrator",
        environment=settings.environment,
        dependencies=dependencies,
    )
