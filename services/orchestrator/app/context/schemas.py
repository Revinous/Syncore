from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

ContextSectionType = Literal[
    "task",
    "constraint",
    "baton",
    "routing",
    "memory",
    "project_event",
    "tool_output",
    "log_output",
    "file_content",
    "error",
    "schema",
    "code_patch",
    "prior_bundle",
    "summary",
    "other",
]


class ContextSection(BaseModel):
    section_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    section_type: ContextSectionType = "other"
    content: str = Field(min_length=1)
    source: str | None = None
    is_critical: bool = False
    priority: int = Field(default=50, ge=0, le=100)
    created_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RawContextBundle(BaseModel):
    task_id: UUID
    target_agent: str = Field(min_length=1)
    target_model: str = Field(min_length=1)
    token_budget: int = Field(ge=256, le=200_000)
    sections: list[ContextSection] = Field(default_factory=list)
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = Field(default_factory=dict)


class ContextReference(BaseModel):
    ref_id: str = Field(min_length=1)
    task_id: UUID
    content_type: str = Field(min_length=1)
    original_content: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    retrieval_hint: str = Field(min_length=1)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContextOptimizationPolicy(BaseModel):
    token_budget: int = Field(ge=256, le=200_000)
    layering_enabled: bool = False
    preserve_section_types: set[ContextSectionType] = Field(default_factory=set)
    large_content_threshold_chars: int = Field(default=2_000, ge=500)
    max_baton_chars: int = Field(default=3_500, ge=512)
    recent_events_full_count: int = Field(default=4, ge=0, le=100)
    max_event_summary_chars: int = Field(default=400, ge=80)
    max_noncritical_chars: int = Field(default=700, ge=120)
    critical_markers: tuple[str, ...] = (
        "DO NOT",
        "MUST",
        "REQUIRED",
        "constraint",
        "error",
        "exception",
        "traceback",
        "schema",
        "patch",
        "diff --git",
    )


class OptimizedContextBundle(BaseModel):
    bundle_id: UUID | None = None
    task_id: UUID
    target_agent: str = Field(min_length=1)
    target_model: str = Field(min_length=1)
    token_budget: int = Field(ge=256, le=200_000)
    estimated_token_count: int = Field(ge=0)
    raw_estimated_token_count: int = Field(default=0, ge=0)
    token_savings_estimate: int = Field(default=0)
    token_savings_pct: float = Field(default=0.0)
    estimated_cost_raw_usd: float | None = None
    estimated_cost_optimized_usd: float | None = None
    estimated_cost_saved_usd: float | None = None
    optimized_context: dict[str, Any] = Field(default_factory=dict)
    sections: list[ContextSection] = Field(default_factory=list)
    included_refs: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ContextAssembleOptimizedRequest(BaseModel):
    task_id: UUID
    target_agent: str = Field(min_length=1)
    target_model: str = Field(min_length=1)
    token_budget: int = Field(default=8_000, ge=256, le=200_000)
