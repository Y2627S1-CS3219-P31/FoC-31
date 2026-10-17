# AI-INFLUENCED: Generalize deletion tasks into credit-release workflows with Codex.
"""Add one credit-release outbox for delete, cancel, and expire actions."""

import sqlalchemy as sa
from alembic import op

revision = "20261016_order_release_outbox"
down_revision = "20261016_order_event_outbox"
branch_labels = None
depends_on = None

TABLE_NAME = "order_release_outbox"
LEGACY_TABLE_NAME = "order_deletion_outbox"
LEGACY_TEMP_TABLE_NAME = "order_deletion_outbox_legacy"


def _create_table() -> None:
    op.create_table(
        TABLE_NAME,
        sa.Column("task_id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("reservation_id", sa.String(36), nullable=False),
        sa.Column("requester_id", sa.String(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(255)),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.CheckConstraint(
            "action IN ('delete', 'cancel', 'expire')",
            name="ck_order_release_outbox_action",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'completed', 'failed')",
            name="ck_order_release_outbox_status",
        ),
    )


def _create_indexes() -> None:
    op.create_index("ix_order_release_outbox_order_id", TABLE_NAME, ["order_id"])
    op.create_index("ix_order_release_outbox_reservation_id", TABLE_NAME, ["reservation_id"])
    op.create_index(
        "uq_order_release_outbox_pending_order",
        TABLE_NAME,
        ["order_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )
    op.create_index(
        "uq_order_release_outbox_pending_reservation",
        TABLE_NAME,
        ["reservation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
        sqlite_where=sa.text("status = 'pending'"),
    )


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    tables = inspector.get_table_names()
    if TABLE_NAME in tables:
        return

    if LEGACY_TABLE_NAME in tables:
        op.rename_table(LEGACY_TABLE_NAME, LEGACY_TEMP_TABLE_NAME)
        _create_table()
        # Rebuilding removes the legacy one-task-per-order constraint. The new
        # constraint applies only while a release action is pending.
        op.execute(
            sa.text(
                f"""
                INSERT INTO {TABLE_NAME} (
                    task_id, order_id, reservation_id, requester_id, action,
                    status, reason, published_at, attempts, last_error, created_at
                )
                SELECT
                    task_id, order_id, reservation_id, requester_id, 'delete',
                    CASE WHEN status = 'processing' THEN 'pending' ELSE status END,
                    NULL, NULL, attempts, last_error, created_at
                FROM {LEGACY_TEMP_TABLE_NAME}
                """
            )
        )
        op.drop_table(LEGACY_TEMP_TABLE_NAME)
        _create_indexes()
        return

    _create_table()
    _create_indexes()


def downgrade() -> None:
    if TABLE_NAME not in sa.inspect(op.get_bind()).get_table_names():
        return
    op.drop_table(TABLE_NAME)
