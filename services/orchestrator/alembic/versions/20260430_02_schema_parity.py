"""schema parity for queue, autonomy snapshots, context layering, research and notifications

Revision ID: 20260430_02
Revises: 20260428_01
Create Date: 2026-04-30
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "20260430_02"
down_revision = "20260428_01"
branch_labels = None
depends_on = None


def _has_table(name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return name in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for col in inspector.get_columns(table):
        if col.get("name") == column:
            return True
    return False


def _has_index(table: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(idx.get("name") == index_name for idx in inspector.get_indexes(table))


def upgrade() -> None:
    if not _has_table("context_reference_layers"):
        op.create_table(
            "context_reference_layers",
            sa.Column("layer_id", sa.String(length=64), primary_key=True),
            sa.Column("ref_id", sa.String(length=128), nullable=False),
            sa.Column("layer", sa.String(length=32), nullable=False),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["ref_id"], ["context_references.ref_id"], ondelete="CASCADE"),
            sa.UniqueConstraint("ref_id", "layer", name="uq_context_reference_layers_ref_layer"),
        )

    if _has_table("context_bundles"):
        if not _has_column("context_bundles", "raw_estimated_tokens"):
            op.add_column(
                "context_bundles",
                sa.Column(
                    "raw_estimated_tokens",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if not _has_column("context_bundles", "optimized_estimated_tokens"):
            op.add_column(
                "context_bundles",
                sa.Column(
                    "optimized_estimated_tokens",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if not _has_column("context_bundles", "token_savings_estimate"):
            op.add_column(
                "context_bundles",
                sa.Column(
                    "token_savings_estimate",
                    sa.Integer(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if not _has_column("context_bundles", "token_savings_pct"):
            op.add_column(
                "context_bundles",
                sa.Column(
                    "token_savings_pct",
                    sa.Float(),
                    nullable=False,
                    server_default="0",
                ),
            )
        if not _has_column("context_bundles", "estimated_cost_raw_usd"):
            op.add_column(
                "context_bundles",
                sa.Column("estimated_cost_raw_usd", sa.Float(), nullable=True),
            )
        if not _has_column("context_bundles", "estimated_cost_optimized_usd"):
            op.add_column(
                "context_bundles",
                sa.Column("estimated_cost_optimized_usd", sa.Float(), nullable=True),
            )
        if not _has_column("context_bundles", "estimated_cost_saved_usd"):
            op.add_column(
                "context_bundles",
                sa.Column("estimated_cost_saved_usd", sa.Float(), nullable=True),
            )

    if not _has_table("run_queue"):
        op.create_table(
            "run_queue",
            sa.Column("job_id", sa.String(length=64), primary_key=True),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.Text(), nullable=False),
            sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("last_error", sa.Text(), nullable=True),
            sa.Column("run_id", sa.String(length=64), nullable=True),
            sa.Column("available_at", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        )

    if not _has_table("autonomy_snapshots"):
        op.create_table(
            "autonomy_snapshots",
            sa.Column("snapshot_id", sa.String(length=64), primary_key=True),
            sa.Column("task_id", sa.String(length=64), nullable=False),
            sa.Column("cycle", sa.Integer(), nullable=False),
            sa.Column("stage", sa.String(length=64), nullable=False),
            sa.Column("state", sa.String(length=64), nullable=False),
            sa.Column("strategy", sa.String(length=64), nullable=False),
            sa.Column("quality_score", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("details", sa.Text(), nullable=False, server_default="{}"),
            sa.Column("created_at", sa.Text(), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        )

    if _has_table("research_findings"):
        if not _has_column("research_findings", "source"):
            op.add_column(
                "research_findings",
                sa.Column(
                    "source",
                    sa.String(length=64),
                    nullable=False,
                    server_default="researcher",
                ),
            )
    else:
        op.create_table(
            "research_findings",
            sa.Column("finding_id", sa.String(length=64), primary_key=True),
            sa.Column("task_id", sa.String(length=64), nullable=True),
            sa.Column("workspace_id", sa.String(length=64), nullable=True),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("summary", sa.Text(), nullable=False),
            sa.Column("details", sa.Text(), nullable=False),
            sa.Column(
                "impact_level",
                sa.String(length=16),
                nullable=False,
                server_default="medium",
            ),
            sa.Column("source", sa.String(length=64), nullable=False, server_default="researcher"),
            sa.Column("created_at", sa.Text(), nullable=False),
        )

    if _has_table("notifications"):
        if not _has_column("notifications", "finding_id"):
            op.add_column(
                "notifications",
                sa.Column("finding_id", sa.String(length=64), nullable=True),
            )
    else:
        op.create_table(
            "notifications",
            sa.Column("id", sa.String(length=64), primary_key=True),
            sa.Column("category", sa.String(length=64), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("body", sa.Text(), nullable=False),
            sa.Column("related_task_id", sa.String(length=64), nullable=True),
            sa.Column("related_workspace_id", sa.String(length=64), nullable=True),
            sa.Column("finding_id", sa.String(length=64), nullable=True),
            sa.Column(
                "acknowledged",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
            sa.Column("acknowledged_at", sa.Text(), nullable=True),
            sa.Column("created_at", sa.Text(), nullable=False),
        )

    if _has_table("context_reference_layers") and not _has_index(
        "context_reference_layers", "idx_context_reference_layers_ref_id_layer"
    ):
        op.create_index(
            "idx_context_reference_layers_ref_id_layer",
            "context_reference_layers",
            ["ref_id", "layer"],
        )
    if _has_table("run_queue") and not _has_index(
        "run_queue", "idx_run_queue_status_available_created"
    ):
        op.create_index(
            "idx_run_queue_status_available_created",
            "run_queue",
            ["status", "available_at", "created_at"],
        )
    if _has_table("autonomy_snapshots") and not _has_index(
        "autonomy_snapshots", "idx_autonomy_snapshots_task_created"
    ):
        op.create_index(
            "idx_autonomy_snapshots_task_created",
            "autonomy_snapshots",
            ["task_id", "created_at"],
        )
    if _has_table("research_findings") and not _has_index(
        "research_findings", "idx_research_findings_task_created"
    ):
        op.create_index(
            "idx_research_findings_task_created",
            "research_findings",
            ["task_id", "created_at"],
        )
    if _has_table("notifications") and not _has_index(
        "notifications", "idx_notifications_ack_created"
    ):
        op.create_index(
            "idx_notifications_ack_created",
            "notifications",
            ["acknowledged", "created_at"],
        )


def downgrade() -> None:
    if _has_index("notifications", "idx_notifications_ack_created"):
        op.drop_index("idx_notifications_ack_created", table_name="notifications")
    if _has_index("research_findings", "idx_research_findings_task_created"):
        op.drop_index("idx_research_findings_task_created", table_name="research_findings")
    if _has_index("autonomy_snapshots", "idx_autonomy_snapshots_task_created"):
        op.drop_index("idx_autonomy_snapshots_task_created", table_name="autonomy_snapshots")
    if _has_index("run_queue", "idx_run_queue_status_available_created"):
        op.drop_index("idx_run_queue_status_available_created", table_name="run_queue")
    if _has_index("context_reference_layers", "idx_context_reference_layers_ref_id_layer"):
        op.drop_index(
            "idx_context_reference_layers_ref_id_layer",
            table_name="context_reference_layers",
        )

    if _has_table("autonomy_snapshots"):
        op.drop_table("autonomy_snapshots")
    if _has_table("run_queue"):
        op.drop_table("run_queue")
    if _has_table("context_reference_layers"):
        op.drop_table("context_reference_layers")
