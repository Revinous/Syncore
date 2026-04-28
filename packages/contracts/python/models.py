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
AgentRole = Literal["planner", "coder", "reviewer", "analyst", "memory"]
AgentRunStatus = Literal["queued", "running", "blocked", "completed", "failed"]
RunStreamEventType = Literal["started", "chunk", "completed", "error"]
WorkspaceRuntimeMode = Literal["docker", "native", "unknown"]


class TaskCreate(BaseModel):
    title: str = Field(min_length=1)
    task_type: TaskType
    complexity: ComplexityLevel = "medium"
    workspace_id: UUID | None = None


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1)
    status: TaskStatus | None = None
    task_type: TaskType | None = None
    complexity: ComplexityLevel | None = None
    workspace_id: UUID | None = None


class Task(BaseModel):
    id: UUID
    title: str = Field(min_length=1)
    status: TaskStatus = "new"
    task_type: TaskType = "analysis"
    complexity: ComplexityLevel = "medium"
    workspace_id: UUID | None = None
    created_at: datetime
    updated_at: datetime


class BatonPayload(BaseModel):
    objective: str = Field(min_length=1)
    completed_work: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    next_best_action: str = Field(min_length=1)
    relevant_artifacts: list[str] = Field(default_factory=list)


class BatonPacketCreate(BaseModel):
    task_id: UUID
    from_agent: str = Field(min_length=1)
    to_agent: str | None = None
    summary: str = Field(min_length=1)
    payload: BatonPayload


class BatonPacket(BaseModel):
    id: UUID
    task_id: UUID
    from_agent: str = Field(min_length=1)
    to_agent: str | None = None
    summary: str = Field(min_length=1)
    payload: BatonPayload
    created_at: datetime


class ProjectEventCreate(BaseModel):
    task_id: UUID
    event_type: str = Field(min_length=1)
    event_data: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ProjectEvent(BaseModel):
    id: UUID
    task_id: UUID
    event_type: str = Field(min_length=1)
    event_data: dict[str, str | int | float | bool | None]
    created_at: datetime


class AgentRunCreate(BaseModel):
    task_id: UUID
    role: AgentRole
    status: AgentRunStatus = "queued"
    input_summary: str | None = None


class AgentRunUpdate(BaseModel):
    status: AgentRunStatus | None = None
    output_summary: str | None = None
    error_message: str | None = None


class AgentRun(BaseModel):
    id: UUID
    task_id: UUID
    role: AgentRole
    status: AgentRunStatus
    input_summary: str | None = None
    output_summary: str | None = None
    error_message: str | None = None
    created_at: datetime
    updated_at: datetime


class AnalystDigestRequest(BaseModel):
    task_id: UUID
    limit: int = Field(default=50, ge=1, le=200)


class TaskDetail(BaseModel):
    task: Task
    agent_runs: list[AgentRun]
    baton_packets: list[BatonPacket]
    event_count: int = Field(ge=0)
    digest_path: str


class MemoryLookupRequest(BaseModel):
    task_id: UUID
    limit: int = Field(default=20, ge=1, le=200)


class MemoryLookupResponse(BaseModel):
    task_id: UUID
    latest_baton_packet: BatonPacket | None
    recent_events: list[ProjectEvent]
    event_count: int = Field(ge=0)


class ContextAssembleRequest(BaseModel):
    task_id: UUID
    event_limit: int = Field(default=20, ge=1, le=200)


class ContextBundle(BaseModel):
    task: Task
    latest_baton_packet: BatonPacket | None
    recent_events: list[ProjectEvent]
    objective: str | None = None
    completed_work: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    next_best_action: str | None = None
    relevant_artifacts: list[str] = Field(default_factory=list)


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


class RunExecutionRequest(BaseModel):
    task_id: UUID
    prompt: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    target_model: str = Field(min_length=1)
    token_budget: int = Field(default=8_000, ge=256, le=200_000)
    provider: str | None = None
    idempotency_key: str | None = None
    agent_role: AgentRole = "coder"
    system_prompt: str | None = None
    max_output_tokens: int = Field(default=1_200, ge=64, le=64_000)
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    timeout_seconds: int | None = Field(default=None, ge=5, le=600)


class RunExecutionResponse(BaseModel):
    run_id: UUID
    task_id: UUID
    status: AgentRunStatus
    provider: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    target_model: str = Field(min_length=1)
    output_text: str
    estimated_input_tokens: int = Field(ge=0)
    estimated_output_tokens: int = Field(ge=0)
    total_estimated_tokens: int = Field(ge=0)
    optimized_bundle_id: UUID | None = None
    included_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime
    completed_at: datetime


class RunStreamEvent(BaseModel):
    event: RunStreamEventType
    run_id: UUID | None = None
    task_id: UUID | None = None
    provider: str | None = None
    target_model: str | None = None
    content: str | None = None
    estimated_output_tokens: int | None = Field(default=None, ge=0)
    error: str | None = None


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1)
    root_path: str = Field(min_length=1)
    repo_url: str | None = None
    branch: str | None = None
    runtime_mode: WorkspaceRuntimeMode = "native"
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorkspaceUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1)
    root_path: str | None = Field(default=None, min_length=1)
    repo_url: str | None = None
    branch: str | None = None
    runtime_mode: WorkspaceRuntimeMode | None = None
    metadata: dict[str, Any] | None = None


class Workspace(BaseModel):
    id: UUID
    name: str = Field(min_length=1)
    root_path: str = Field(min_length=1)
    repo_url: str | None = None
    branch: str | None = None
    runtime_mode: WorkspaceRuntimeMode = "native"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
