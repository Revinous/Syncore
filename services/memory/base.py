from __future__ import annotations

from typing import Protocol
from uuid import UUID

from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    BatonPacket,
    BatonPacketCreate,
    ProjectEvent,
    ProjectEventCreate,
    Task,
    TaskCreate,
    TaskUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
)


class MemoryStoreProtocol(Protocol):
    def create_task(self, task: TaskCreate) -> Task: ...

    def get_task(self, task_id: UUID) -> Task | None: ...

    def list_tasks(self, limit: int = 50) -> list[Task]: ...

    def update_task(self, task_id: UUID, payload: TaskUpdate) -> Task | None: ...

    def create_agent_run(self, run: AgentRunCreate) -> AgentRun: ...

    def update_agent_run(
        self, run_id: UUID, update: AgentRunUpdate
    ) -> AgentRun | None: ...

    def get_agent_run(self, run_id: UUID) -> AgentRun | None: ...

    def list_agent_runs(
        self, task_id: UUID | None = None, limit: int = 50
    ) -> list[AgentRun]: ...

    def save_baton_packet(self, packet: BatonPacketCreate) -> BatonPacket: ...

    def get_baton_packet(self, packet_id: UUID) -> BatonPacket | None: ...

    def get_latest_baton_packet(self, task_id: UUID) -> BatonPacket | None: ...

    def list_baton_packets(
        self, task_id: UUID, limit: int = 20
    ) -> list[BatonPacket]: ...

    def save_project_event(self, event: ProjectEventCreate) -> ProjectEvent: ...

    def list_project_events(
        self, task_id: UUID | None = None, limit: int = 50
    ) -> list[ProjectEvent]: ...

    def count_project_events(self, task_id: UUID) -> int: ...

    def upsert_context_reference(
        self,
        *,
        ref_id: str,
        task_id: UUID,
        content_type: str,
        original_content: str,
        summary: str,
        retrieval_hint: str,
    ) -> dict[str, object]: ...

    def get_context_reference(self, ref_id: str) -> dict[str, object] | None: ...

    def save_context_bundle(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
        optimized_context: dict[str, object],
        included_refs: list[str],
    ) -> dict[str, object]: ...

    def get_latest_context_bundle(self, task_id: UUID) -> dict[str, object] | None: ...

    def create_workspace(self, payload: WorkspaceCreate) -> Workspace: ...

    def get_workspace(self, workspace_id: UUID) -> Workspace | None: ...

    def list_workspaces(self, limit: int = 100) -> list[Workspace]: ...

    def update_workspace(
        self, workspace_id: UUID, payload: WorkspaceUpdate
    ) -> Workspace | None: ...

    def delete_workspace(self, workspace_id: UUID) -> bool: ...
