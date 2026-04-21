from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from packages.contracts.python.models import ExecutiveDigest
from services.analyst.digest import AnalystDigestService
from services.memory.store import MemoryStore

from app.config import Settings, get_settings

router = APIRouter(prefix="/analyst", tags=["analyst"])


def get_memory_store(settings: Settings = Depends(get_settings)) -> MemoryStore:
    return MemoryStore(settings.postgres_dsn)


def get_digest_service() -> AnalystDigestService:
    return AnalystDigestService()


@router.get("/digest/{task_id}", response_model=ExecutiveDigest)
def get_task_digest(
    task_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    store: MemoryStore = Depends(get_memory_store),
    digest_service: AnalystDigestService = Depends(get_digest_service),
) -> ExecutiveDigest:
    try:
        events = store.list_project_events(task_id=task_id, limit=limit)
    except Exception as error:
        raise HTTPException(
            status_code=503, detail=f"Memory service unavailable: {error}"
        ) from error

    return digest_service.generate_digest(task_id=task_id, events=events)
