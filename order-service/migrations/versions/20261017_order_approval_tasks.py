# AI-INFLUENCED: Order approval task persistence migration implemented with Codex.
"""Add durable order approval tasks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261017_order_approval_tasks"
down_revision = "20261017_order_update_requested"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_approval_tasks",
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=False),
        sa.Column("requester_id", sa.String(), nullable=False),
        sa.Column("courier_id", sa.String(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("last_error", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_order_approval_tasks_status",
        ),
    )
    op.create_index("ix_order_approval_tasks_order_id", "order_approval_tasks", ["order_id"])
    op.create_index(
        "ix_order_approval_tasks_reservation_id", "order_approval_tasks", ["reservation_id"]
    )
    op.create_index(
        "uq_order_approval_tasks_pending_order",
        "order_approval_tasks",
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_table("order_approval_tasks")
