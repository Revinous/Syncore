from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field


class TaskModelSwitchResult(BaseModel):
    task_id: UUID
    previous_provider: str | None = None
    previous_model: str | None = None
    preferred_provider: str = Field(min_length=1)
    preferred_model: str = Field(min_length=1)
    target_agent: str = Field(min_length=1)
    token_budget: int = Field(ge=256, le=200_000)
    context_bundle_id: UUID
    estimated_token_count: int = Field(ge=0)
    included_refs: list[str] = Field(default_factory=list)
    continuity_status: str = "preserved"
    continuity_notes: list[str] = Field(default_factory=list)


class ChildTaskStatusItem(BaseModel):
    task_id: UUID
    title: str
    status: str
    task_type: str
    complexity: str
    updated_at: str


class ChildTaskStatusBoard(BaseModel):
    parent_task_id: UUID
    has_children: bool
    total_children: int = Field(ge=0)
    completed_children: int = Field(ge=0)
    blocked_children: int = Field(ge=0)
    active_children: int = Field(ge=0)
    children: list[ChildTaskStatusItem] = Field(default_factory=list)


class TaskModelSwitchRecord(BaseModel):
    switched_at: str
    from_provider: str | None = None
    from_model: str | None = None
    to_provider: str
    to_model: str
    target_agent: str | None = None
    continuity_status: str | None = None
    context_bundle_id: str | None = None


class TaskModelPolicyStage(BaseModel):
    provider: str | None = None
    model: str | None = None


class TaskModelPolicy(BaseModel):
    default_provider: str
    default_model: str
    plan: TaskModelPolicyStage = Field(default_factory=TaskModelPolicyStage)
    execute: TaskModelPolicyStage = Field(default_factory=TaskModelPolicyStage)
    review: TaskModelPolicyStage = Field(default_factory=TaskModelPolicyStage)
    fallback_order: list[str] = Field(default_factory=list)
    prefer_reviewer_provider: bool = True
    optimization_goal: str = "balanced"
    allow_cross_provider_switching: bool = True
    maintain_context_continuity: bool = True
    minimum_context_window: int = 0
    max_latency_tier: str | None = None
    max_cost_tier: str | None = None


class TaskModelPolicyUpdate(BaseModel):
    default_provider: str | None = None
    default_model: str | None = None
    plan_provider: str | None = None
    plan_model: str | None = None
    execute_provider: str | None = None
    execute_model: str | None = None
    review_provider: str | None = None
    review_model: str | None = None
    fallback_order: list[str] | None = None
    prefer_reviewer_provider: bool | None = None
    optimization_goal: str | None = None
    allow_cross_provider_switching: bool | None = None
    maintain_context_continuity: bool | None = None
    minimum_context_window: int | None = None
    max_latency_tier: str | None = None
    max_cost_tier: str | None = None


class TaskExecutionArtifact(BaseModel):
    ref_id: str
    path: str
    content_type: str
    summary: str
    retrieval_hint: str
    preview: str
    created_at: str


class TaskExecutionCommand(BaseModel):
    command: str
    status: str
    output_preview: str | None = None


class TaskExecutionRunOutput(BaseModel):
    run_id: UUID
    role: str
    status: str
    provider: str | None = None
    target_model: str | None = None
    output_ref_id: str | None = None
    output_preview: str | None = None
    error_message: str | None = None
    updated_at: str


class TaskExecutionReport(BaseModel):
    task_id: UUID
    outcome_status: str
    summary_reason: str
    meaningful_change: bool = False
    changed_files: list[str] = Field(default_factory=list)
    planned_actions: list[str] = Field(default_factory=list)
    verification_status: str | None = None
    verification_reason: str | None = None
    verification_commands: list[TaskExecutionCommand] = Field(default_factory=list)
    diff_artifacts: list[TaskExecutionArtifact] = Field(default_factory=list)
    output_artifacts: list[TaskExecutionRunOutput] = Field(default_factory=list)
    report_ref_id: str | None = None
    last_event_type: str | None = None
    last_updated_at: str | None = None
