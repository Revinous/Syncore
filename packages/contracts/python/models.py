from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


TaskStatus = Literal["new", "in_progress", "blocked", "completed"]


class Task(BaseModel):
    id: UUID
    title: str = Field(min_length=1)
    status: TaskStatus = "new"
    created_at: datetime
    updated_at: datetime


class BatonPacket(BaseModel):
    id: UUID
    task_id: UUID
    from_agent: str = Field(min_length=1)
    to_agent: str | None = None
    summary: str = Field(min_length=1)
    payload: dict[str, Any]
    created_at: datetime


class ProjectEvent(BaseModel):
    id: UUID
    task_id: UUID
    event_type: str = Field(min_length=1)
    event_data: dict[str, Any]
    created_at: datetime
