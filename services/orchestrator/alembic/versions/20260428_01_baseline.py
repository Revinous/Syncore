"""baseline schema

Revision ID: 20260428_01
Revises: None
Create Date: 2026-04-28
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260428_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="new"),
        sa.Column("task_type", sa.String(length=32), nullable=False, server_default="analysis"),
        sa.Column("complexity", sa.String(length=32), nullable=False, server_default="medium"),
        sa.Column("workspace_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "agent_runs",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "baton_packets",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("from_agent", sa.String(length=64), nullable=False),
        sa.Column("to_agent", sa.String(length=64), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "project_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("event_data", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "workspaces",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("root_path", sa.Text(), nullable=False),
        sa.Column("repo_url", sa.Text(), nullable=True),
        sa.Column("branch", sa.String(length=255), nullable=True),
        sa.Column("runtime_mode", sa.String(length=32), nullable=False, server_default="native"),
        sa.Column("metadata", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "context_references",
        sa.Column("ref_id", sa.String(length=128), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("original_content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("retrieval_hint", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_table(
        "context_bundles",
        sa.Column("bundle_id", sa.String(length=128), primary_key=True),
        sa.Column("task_id", sa.String(length=64), nullable=False),
        sa.Column("target_agent", sa.String(length=64), nullable=False),
        sa.Column("target_model", sa.String(length=128), nullable=False),
        sa.Column("token_budget", sa.Integer(), nullable=False),
        sa.Column("optimized_context", sa.Text(), nullable=False),
        sa.Column("included_refs", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.Text(), nullable=False),
    )

    op.create_index(
        "idx_agent_runs_task_id_created_at",
        "agent_runs",
        ["task_id", "created_at"],
    )
    op.create_index("idx_tasks_workspace_id", "tasks", ["workspace_id"])
    op.create_index(
        "idx_baton_packets_task_id_created_at",
        "baton_packets",
        ["task_id", "created_at"],
    )
    op.create_index(
        "idx_project_events_task_id_created_at",
        "project_events",
        ["task_id", "created_at"],
    )
    op.create_index("idx_workspaces_root_path", "workspaces", ["root_path"])
    op.create_index(
        "idx_context_references_task_id_created_at",
        "context_references",
        ["task_id", "created_at"],
    )
    op.create_index(
        "idx_context_bundles_task_id_created_at",
        "context_bundles",
        ["task_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_context_bundles_task_id_created_at", table_name="context_bundles")
    op.drop_index("idx_context_references_task_id_created_at", table_name="context_references")
    op.drop_index("idx_workspaces_root_path", table_name="workspaces")
    op.drop_index("idx_project_events_task_id_created_at", table_name="project_events")
    op.drop_index("idx_baton_packets_task_id_created_at", table_name="baton_packets")
    op.drop_index("idx_tasks_workspace_id", table_name="tasks")
    op.drop_index("idx_agent_runs_task_id_created_at", table_name="agent_runs")

    op.drop_table("context_bundles")
    op.drop_table("context_references")
    op.drop_table("workspaces")
    op.drop_table("project_events")
    op.drop_table("baton_packets")
    op.drop_table("agent_runs")
    op.drop_table("tasks")
