# AI-influenced: implemented with Codex; see ai/usage-log.md.
"""add order ownership and assignment

Revision ID: 7c4d92f45a11
Revises: 72a10783d06a
Create Date: 2026-09-26 03:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "7c4d92f45a11"
down_revision: str | Sequence[str] | None = "72a10783d06a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("requester_id", sa.String(), nullable=False))
    op.add_column("orders", sa.Column("courier_id", sa.String(), nullable=True))
    op.execute("UPDATE orders SET status = UPPER(status)")
    op.alter_column(
        "orders",
        "status",
        existing_type=sa.String(),
        server_default="OPEN",
        existing_nullable=False,
    )
    op.create_check_constraint("ck_orders_reward_positive", "orders", "reward > 0")
    op.create_index("ix_orders_requester_id", "orders", ["requester_id"], unique=False)
    op.create_index("ix_orders_courier_id", "orders", ["courier_id"], unique=False)
    op.create_index(
        "ix_orders_available",
        "orders",
        ["status", "courier_id", "deadline"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_orders_available", table_name="orders")
    op.drop_index("ix_orders_courier_id", table_name="orders")
    op.drop_index("ix_orders_requester_id", table_name="orders")
    op.drop_constraint("ck_orders_reward_positive", "orders", type_="check")
    op.alter_column(
        "orders",
        "status",
        existing_type=sa.String(),
        server_default="open",
        existing_nullable=False,
    )
    op.execute("UPDATE orders SET status = LOWER(status)")
    op.drop_column("orders", "courier_id")
    op.drop_column("orders", "requester_id")
