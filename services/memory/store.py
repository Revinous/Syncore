from contextlib import contextmanager
from typing import Iterator
from uuid import UUID

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

from packages.contracts.python.models import (
    AgentRun,
    AgentRunCreate,
    AgentRunUpdate,
    BatonPacket,
    BatonPacketCreate,
    ProjectEvent,
    ProjectEventCreate,
    ResearchFinding,
    ResearchFindingCreate,
    Task,
    TaskCreate,
    TaskUpdate,
    Workspace,
    WorkspaceCreate,
    WorkspaceUpdate,
    Notification,
)


class MemoryStore:
    def __init__(self, postgres_dsn: str) -> None:
        self._postgres_dsn = postgres_dsn

    @contextmanager
    def _cursor(self) -> Iterator[psycopg.Cursor]:
        with psycopg.connect(self._postgres_dsn, row_factory=dict_row) as connection:
            with connection.cursor() as cursor:
                yield cursor
            connection.commit()

    def create_task(self, task: TaskCreate) -> Task:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO tasks (title, task_type, complexity, workspace_id)
                VALUES (%s, %s, %s, %s)
                RETURNING id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                """,
                (task.title, task.task_type, task.complexity, task.workspace_id),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to create task")

        return Task.model_validate(row)

    def get_task(self, task_id: UUID) -> Task | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                FROM tasks
                WHERE id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return Task.model_validate(row)

    def list_tasks(self, limit: int = 50, workspace_id: UUID | None = None) -> list[Task]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            if workspace_id is None:
                cursor.execute(
                    """
                    SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                    FROM tasks
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (bounded_limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                    FROM tasks
                    WHERE workspace_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (workspace_id, bounded_limit),
                )
            rows = cursor.fetchall()

        return [Task.model_validate(row) for row in rows]

    def update_task(self, task_id: UUID, payload: TaskUpdate) -> Task | None:
        assignments: list[str] = []
        values: list[object] = []

        if payload.title is not None:
            assignments.append("title = %s")
            values.append(payload.title)
        if payload.status is not None:
            assignments.append("status = %s")
            values.append(payload.status)
        if payload.task_type is not None:
            assignments.append("task_type = %s")
            values.append(payload.task_type)
        if payload.complexity is not None:
            assignments.append("complexity = %s")
            values.append(payload.complexity)
        if "workspace_id" in payload.model_fields_set:
            assignments.append("workspace_id = %s")
            values.append(payload.workspace_id)

        if not assignments:
            raise ValueError("At least one field must be provided for task update")

        assignments.append("updated_at = NOW()")
        values.append(task_id)

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE tasks
                SET {", ".join(assignments)}
                WHERE id = %s
                RETURNING id, title, status, task_type, complexity, workspace_id, created_at, updated_at
                """,
                tuple(values),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return Task.model_validate(row)

    def create_agent_run(self, run: AgentRunCreate) -> AgentRun:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO agent_runs (task_id, role, status, input_summary)
                VALUES (%s, %s, %s, %s)
                RETURNING id, task_id, role, status, input_summary, output_summary,
                          error_message, created_at, updated_at
                """,
                (run.task_id, run.role, run.status, run.input_summary),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to create agent run")

        return AgentRun.model_validate(row)

    def update_agent_run(self, run_id: UUID, update: AgentRunUpdate) -> AgentRun | None:
        assignments: list[str] = []
        values: list[object] = []

        if update.status is not None:
            assignments.append("status = %s")
            values.append(update.status)
        if update.output_summary is not None:
            assignments.append("output_summary = %s")
            values.append(update.output_summary)
        if update.error_message is not None:
            assignments.append("error_message = %s")
            values.append(update.error_message)

        if not assignments:
            raise ValueError("At least one field must be provided for run update")

        assignments.append("updated_at = NOW()")
        values.append(run_id)

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE agent_runs
                SET {", ".join(assignments)}
                WHERE id = %s
                RETURNING id, task_id, role, status, input_summary, output_summary,
                          error_message, created_at, updated_at
                """,
                tuple(values),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return AgentRun.model_validate(row)

    def get_agent_run(self, run_id: UUID) -> AgentRun | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, role, status, input_summary, output_summary,
                       error_message, created_at, updated_at
                FROM agent_runs
                WHERE id = %s
                """,
                (run_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return AgentRun.model_validate(row)

    def list_agent_runs(
        self, task_id: UUID | None = None, limit: int = 50
    ) -> list[AgentRun]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            if task_id is None:
                cursor.execute(
                    """
                    SELECT id, task_id, role, status, input_summary, output_summary,
                           error_message, created_at, updated_at
                    FROM agent_runs
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (bounded_limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, task_id, role, status, input_summary, output_summary,
                           error_message, created_at, updated_at
                    FROM agent_runs
                    WHERE task_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (task_id, bounded_limit),
                )
            rows = cursor.fetchall()

        return [AgentRun.model_validate(row) for row in rows]

    def save_baton_packet(self, packet: BatonPacketCreate) -> BatonPacket:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO baton_packets (task_id, from_agent, to_agent, summary, payload)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, task_id, from_agent, to_agent, summary, payload, created_at
                """,
                (
                    packet.task_id,
                    packet.from_agent,
                    packet.to_agent,
                    packet.summary,
                    Json(packet.payload.model_dump()),
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist baton packet")

        return BatonPacket.model_validate(row)

    def get_baton_packet(self, packet_id: UUID) -> BatonPacket | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE id = %s
                """,
                (packet_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return BatonPacket.model_validate(row)

    def get_latest_baton_packet(self, task_id: UUID) -> BatonPacket | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None

        return BatonPacket.model_validate(row)

    def list_baton_packets(self, task_id: UUID, limit: int = 20) -> list[BatonPacket]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, task_id, from_agent, to_agent, summary, payload, created_at
                FROM baton_packets
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (task_id, bounded_limit),
            )
            rows = cursor.fetchall()

        return [BatonPacket.model_validate(row) for row in rows]

    def save_project_event(self, event: ProjectEventCreate) -> ProjectEvent:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO project_events (task_id, event_type, event_data)
                VALUES (%s, %s, %s)
                RETURNING id, task_id, event_type, event_data, created_at
                """,
                (
                    event.task_id,
                    event.event_type,
                    Json(event.event_data),
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist project event")

        return ProjectEvent.model_validate(row)

    def list_project_events(
        self, task_id: UUID | None = None, limit: int = 50
    ) -> list[ProjectEvent]:
        bounded_limit = min(max(limit, 1), 200)
        with self._cursor() as cursor:
            if task_id is None:
                cursor.execute(
                    """
                    SELECT id, task_id, event_type, event_data, created_at
                    FROM project_events
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (bounded_limit,),
                )
            else:
                cursor.execute(
                    """
                    SELECT id, task_id, event_type, event_data, created_at
                    FROM project_events
                    WHERE task_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (task_id, bounded_limit),
                )
            rows = cursor.fetchall()

        parsed = [ProjectEvent.model_validate(row) for row in rows]
        parsed.reverse()
        return parsed

    def count_project_events(self, task_id: UUID) -> int:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)::int AS total
                FROM project_events
                WHERE task_id = %s
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return 0

        return int(row["total"])

    def create_workspace(self, payload: WorkspaceCreate) -> Workspace:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO workspaces (name, root_path, repo_url, branch, runtime_mode, metadata)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                """,
                (
                    payload.name,
                    payload.root_path,
                    payload.repo_url,
                    payload.branch,
                    payload.runtime_mode,
                    Json(payload.metadata),
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to create workspace")
        return Workspace.model_validate(row)

    def get_workspace(self, workspace_id: UUID) -> Workspace | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM workspaces
                WHERE id = %s
                """,
                (workspace_id,),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return Workspace.model_validate(row)

    def list_workspaces(self, limit: int = 100) -> list[Workspace]:
        bounded_limit = min(max(limit, 1), 500)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM workspaces
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = cursor.fetchall()

        return [Workspace.model_validate(row) for row in rows]

    def update_workspace(
        self, workspace_id: UUID, payload: WorkspaceUpdate
    ) -> Workspace | None:
        assignments: list[str] = []
        values: list[object] = []

        if payload.name is not None:
            assignments.append("name = %s")
            values.append(payload.name)
        if payload.root_path is not None:
            assignments.append("root_path = %s")
            values.append(payload.root_path)
        if payload.repo_url is not None:
            assignments.append("repo_url = %s")
            values.append(payload.repo_url)
        if payload.branch is not None:
            assignments.append("branch = %s")
            values.append(payload.branch)
        if payload.runtime_mode is not None:
            assignments.append("runtime_mode = %s")
            values.append(payload.runtime_mode)
        if payload.metadata is not None:
            assignments.append("metadata = %s")
            values.append(Json(payload.metadata))

        if not assignments:
            raise ValueError("At least one field must be provided for workspace update")

        assignments.append("updated_at = NOW()")
        values.append(workspace_id)

        with self._cursor() as cursor:
            cursor.execute(
                f"""
                UPDATE workspaces
                SET {", ".join(assignments)}
                WHERE id = %s
                RETURNING
                    id,
                    name,
                    root_path,
                    repo_url,
                    branch,
                    runtime_mode,
                    metadata,
                    created_at,
                    updated_at
                """,
                tuple(values),
            )
            row = cursor.fetchone()

        if row is None:
            return None
        return Workspace.model_validate(row)

    def delete_workspace(self, workspace_id: UUID) -> bool:
        with self._cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM workspaces
                WHERE id = %s
                """,
                (workspace_id,),
            )
            deleted = cursor.rowcount
        return bool(deleted)

    def create_research_finding(self, payload: ResearchFindingCreate) -> ResearchFinding:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO research_findings (
                    task_id, workspace_id, title, summary, details, impact_level, source
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING finding_id, task_id, workspace_id, title, summary, details, impact_level, source, created_at
                """,
                (
                    payload.task_id,
                    payload.workspace_id,
                    payload.title,
                    payload.summary,
                    payload.details,
                    payload.impact_level,
                    payload.source,
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create research finding")
        return ResearchFinding.model_validate(row)

    def list_research_findings(
        self, task_id: UUID | None = None, workspace_id: UUID | None = None, limit: int = 100
    ) -> list[ResearchFinding]:
        bounded_limit = min(max(limit, 1), 500)
        query = """
            SELECT finding_id, task_id, workspace_id, title, summary, details, impact_level, source, created_at
            FROM research_findings
        """
        clauses: list[str] = []
        values: list[object] = []
        if task_id is not None:
            clauses.append("task_id = %s")
            values.append(task_id)
        if workspace_id is not None:
            clauses.append("workspace_id = %s")
            values.append(workspace_id)
        if clauses:
            query += " WHERE " + " AND ".join(clauses)
        query += " ORDER BY created_at DESC LIMIT %s"
        values.append(bounded_limit)
        with self._cursor() as cursor:
            cursor.execute(query, tuple(values))
            rows = cursor.fetchall()
        return [ResearchFinding.model_validate(row) for row in rows]

    def create_notification(
        self,
        *,
        category: str,
        title: str,
        body: str,
        related_task_id: UUID | None = None,
        related_workspace_id: UUID | None = None,
        finding_id: UUID | None = None,
    ) -> Notification:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notifications (
                    category, title, body, related_task_id, related_workspace_id, finding_id
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                """,
                (category, title, body, related_task_id, related_workspace_id, finding_id),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to create notification")
        return Notification.model_validate(row)

    def list_notifications(
        self, *, acknowledged: bool | None = None, limit: int = 100
    ) -> list[Notification]:
        bounded_limit = min(max(limit, 1), 500)
        query = """
            SELECT id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
            FROM notifications
        """
        values: list[object] = []
        if acknowledged is not None:
            query += " WHERE acknowledged = %s"
            values.append(acknowledged)
        query += " ORDER BY created_at DESC LIMIT %s"
        values.append(bounded_limit)
        with self._cursor() as cursor:
            cursor.execute(query, tuple(values))
            rows = cursor.fetchall()
        return [Notification.model_validate(row) for row in rows]

    def get_notification(self, notification_id: UUID) -> Notification | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                FROM notifications
                WHERE id = %s
                """,
                (notification_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Notification.model_validate(row)

    def acknowledge_notification(self, notification_id: UUID) -> Notification | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                UPDATE notifications
                SET acknowledged = TRUE, acknowledged_at = NOW()
                WHERE id = %s
                RETURNING id, category, title, body, related_task_id, related_workspace_id, finding_id, acknowledged, acknowledged_at, created_at
                """,
                (notification_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Notification.model_validate(row)

    def upsert_context_reference(
        self,
        *,
        ref_id: str,
        task_id: UUID,
        content_type: str,
        original_content: str,
        summary: str,
        retrieval_hint: str,
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO context_references (
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (ref_id) DO UPDATE
                SET
                    summary = EXCLUDED.summary,
                    retrieval_hint = EXCLUDED.retrieval_hint
                RETURNING
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                    created_at
                """,
                (
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist context reference")
        return row

    def get_context_reference(self, ref_id: str) -> dict[str, object] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    ref_id,
                    task_id,
                    content_type,
                    original_content,
                    summary,
                    retrieval_hint,
                    created_at
                FROM context_references
                WHERE ref_id = %s
                """,
                (ref_id,),
            )
            row = cursor.fetchone()
        return row

    def upsert_context_reference_layer(
        self,
        *,
        ref_id: str,
        layer: str,
        content: str,
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO context_reference_layers (ref_id, layer, content)
                VALUES (%s, %s, %s)
                ON CONFLICT (ref_id, layer) DO UPDATE
                SET content = EXCLUDED.content
                RETURNING layer_id, ref_id, layer, content, created_at
                """,
                (ref_id, layer, content),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to persist context reference layer")
        return row

    def get_context_reference_layer(
        self, *, ref_id: str, layer: str
    ) -> dict[str, object] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT layer_id, ref_id, layer, content, created_at
                FROM context_reference_layers
                WHERE ref_id = %s AND layer = %s
                """,
                (ref_id, layer),
            )
            row = cursor.fetchone()
        return row

    def save_context_bundle(
        self,
        *,
        task_id: UUID,
        target_agent: str,
        target_model: str,
        token_budget: int,
        raw_estimated_tokens: int,
        optimized_estimated_tokens: int,
        token_savings_estimate: int,
        token_savings_pct: float,
        estimated_cost_raw_usd: float | None,
        estimated_cost_optimized_usd: float | None,
        estimated_cost_saved_usd: float | None,
        optimized_context: dict[str, object],
        included_refs: list[str],
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO context_bundles (
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    optimized_context,
                    included_refs
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    optimized_context,
                    included_refs,
                    created_at
                """,
                (
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    max(raw_estimated_tokens, 0),
                    max(optimized_estimated_tokens, 0),
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    Json(optimized_context),
                    included_refs,
                ),
            )
            row = cursor.fetchone()

        if row is None:
            raise RuntimeError("Failed to persist optimized context bundle")
        return row

    def get_latest_context_bundle(self, task_id: UUID) -> dict[str, object] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    optimized_context,
                    included_refs,
                    created_at
                FROM context_bundles
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (task_id,),
            )
            row = cursor.fetchone()

        return row

    def list_recent_context_bundles(self, limit: int = 200) -> list[dict[str, object]]:
        bounded_limit = min(max(limit, 1), 1000)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    bundle_id,
                    task_id,
                    target_agent,
                    target_model,
                    token_budget,
                    raw_estimated_tokens,
                    optimized_estimated_tokens,
                    token_savings_estimate,
                    token_savings_pct,
                    estimated_cost_raw_usd,
                    estimated_cost_optimized_usd,
                    estimated_cost_saved_usd,
                    optimized_context,
                    included_refs,
                    created_at
                FROM context_bundles
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (bounded_limit,),
            )
            rows = cursor.fetchall()
        return rows

    def enqueue_run_job(
        self, *, task_id: UUID, payload: dict[str, object], max_attempts: int = 3
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO run_queue (
                    task_id, payload, status, attempt_count, max_attempts,
                    last_error, run_id, available_at
                )
                VALUES (%s, %s, 'queued', 0, %s, NULL, NULL, NOW())
                RETURNING *
                """,
                (task_id, Json(payload), max(1, max_attempts)),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to enqueue run job")
        return row

    def claim_next_run_job(self) -> dict[str, object] | None:
        with self._cursor() as cursor:
            cursor.execute(
                """
                WITH next_job AS (
                    SELECT job_id
                    FROM run_queue
                    WHERE status IN ('queued', 'retry') AND available_at <= NOW()
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE run_queue q
                SET status = 'running', updated_at = NOW()
                FROM next_job
                WHERE q.job_id = next_job.job_id
                RETURNING q.*
                """
            )
            row = cursor.fetchone()
        return row

    def complete_run_job(
        self,
        *,
        job_id: str,
        status: str,
        run_id: UUID | None = None,
        error: str | None = None,
    ) -> dict[str, object] | None:
        next_status = status if status in {"completed", "failed", "retry"} else "failed"
        with self._cursor() as cursor:
            if next_status == "retry":
                cursor.execute(
                    """
                    UPDATE run_queue
                    SET
                        attempt_count = attempt_count + 1,
                        status = CASE WHEN attempt_count + 1 >= max_attempts THEN 'failed' ELSE 'retry' END,
                        last_error = %s,
                        run_id = %s,
                        available_at = NOW(),
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    ((error or "")[:500] if error else None, run_id, job_id),
                )
            else:
                cursor.execute(
                    """
                    UPDATE run_queue
                    SET
                        status = %s,
                        last_error = %s,
                        run_id = %s,
                        available_at = NOW(),
                        updated_at = NOW()
                    WHERE job_id = %s
                    RETURNING *
                    """,
                    (next_status, (error or "")[:500] if error else None, run_id, job_id),
                )
            row = cursor.fetchone()
        return row

    def save_autonomy_snapshot(
        self,
        *,
        task_id: UUID,
        cycle: int,
        stage: str,
        state: str,
        strategy: str,
        quality_score: int,
        details: dict[str, object],
    ) -> dict[str, object]:
        with self._cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO autonomy_snapshots (
                    task_id, cycle, stage, state, strategy, quality_score, details
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                RETURNING *
                """,
                (
                    task_id,
                    max(cycle, 1),
                    stage,
                    state,
                    strategy,
                    max(min(int(quality_score), 100), 0),
                    Json(details),
                ),
            )
            row = cursor.fetchone()
        if row is None:
            raise RuntimeError("Failed to persist autonomy snapshot")
        return row

    def list_autonomy_snapshots(
        self, *, task_id: UUID, limit: int = 200
    ) -> list[dict[str, object]]:
        bounded_limit = min(max(limit, 1), 500)
        with self._cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM autonomy_snapshots
                WHERE task_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (task_id, bounded_limit),
            )
            rows = cursor.fetchall()
        return rows
