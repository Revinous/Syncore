from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI

from app.config import get_settings
from app.observability import log_event


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    log_event("app.startup", environment=settings.environment)
    yield
    log_event("app.shutdown", environment=settings.environment)
