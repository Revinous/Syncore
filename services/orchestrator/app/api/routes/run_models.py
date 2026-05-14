from __future__ import annotations

from uuid import UUID

from packages.contracts.python.models import RunExecutionRequest
from pydantic import BaseModel, Field


class ProviderCapabilityResponse(BaseModel):
    provider: str
    supports_streaming: bool
    supports_system_prompt: bool
    supports_temperature: bool
    supports_max_tokens: bool
    model_hint: str
    max_context_tokens: int
    quality_tier: int
    speed_tier: int
    cost_tier: int
    strengths: list[str]


class QueueEnqueueRequest(BaseModel):
    run: RunExecutionRequest
    max_attempts: int = Field(default=3, ge=1, le=10)


class QueueEnqueueResponse(BaseModel):
    job_id: str
    task_id: str
    status: str
    attempt_count: int
    max_attempts: int


class QueueScanItem(BaseModel):
    job_id: str
    task_id: str
    status: str
    run_id: str | None = None
    note: str


class QueueScanResponse(BaseModel):
    processed: int
    results: list[QueueScanItem]


class WorkspaceRunRequest(BaseModel):
    run: RunExecutionRequest
    max_steps: int = Field(default=3, ge=1, le=8)
    policy_profile: str = Field(default="balanced")
    dry_run: bool = False
    require_approval: bool = False


class AutoRunExecutionRequest(BaseModel):
    task_id: UUID
    stage: str = Field(default="execute", min_length=1)
    prompt: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    token_budget: int = Field(default=8_000, ge=256, le=200_000)
    provider: str | None = None
    target_model: str | None = None
    idempotency_key: str | None = None
    agent_role: str = Field(default="coder", min_length=1)
    system_prompt: str | None = None
    max_output_tokens: int = Field(default=1_200, ge=64, le=64_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)
