from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


TaskStatus = Literal["new", "in_progress", "blocked", "completed"]
TaskType = Literal[
    "analysis",
    "implementation",
    "integration",
    "review",
    "memory_retrieval",
    "memory_update",
]
ComplexityLevel = Literal["low", "medium", "high"]
WorkerRole = Literal["analyst", "orchestrator", "memory"]
ModelTier = Literal["economy", "balanced", "premium"]
RiskLevel = Literal["low", "medium", "high"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    task_type: TaskType
    complexity: ComplexityLevel = "medium"


class Task(BaseModel):
    id: UUID
    title: str = Field(min_length=1)
    status: TaskStatus = "new"
    task_type: TaskType = "analysis"
    complexity: ComplexityLevel = "medium"
    created_at: datetime
    updated_at: datetime


class BatonPacketCreate(BaseModel):
    task_id: UUID
    from_agent: str = Field(min_length=1)
    to_agent: str | None = None
    summary: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)


class BatonPacket(BaseModel):
    id: UUID
    task_id: UUID
    from_agent: str = Field(min_length=1)
    to_agent: str | None = None
    summary: str = Field(min_length=1)
    payload: dict[str, Any]
    created_at: datetime


class ProjectEventCreate(BaseModel):
    task_id: UUID
    event_type: str = Field(min_length=1)
    event_data: dict[str, Any] = Field(default_factory=dict)


class ProjectEvent(BaseModel):
    id: UUID
    task_id: UUID
    event_type: str = Field(min_length=1)
    event_data: dict[str, Any]
    created_at: datetime


class MemoryLookupRequest(BaseModel):
    task_id: UUID
    limit: int = Field(default=20, ge=1, le=200)


class RoutingRequest(BaseModel):
    task_type: TaskType
    complexity: ComplexityLevel
    requires_memory: bool = False


class RoutingDecision(BaseModel):
    worker_role: WorkerRole
    model_tier: ModelTier
    reasoning: str = Field(min_length=1)


class ExecutiveDigest(BaseModel):
    task_id: UUID
    generated_at: datetime
    headline: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    highlights: list[str]
    event_breakdown: dict[str, int]
    risk_level: RiskLevel
    total_events: int = Field(ge=0)
