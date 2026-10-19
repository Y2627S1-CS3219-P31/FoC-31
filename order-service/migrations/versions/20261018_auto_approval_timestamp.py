# AI-INFLUENCED: Record when orders enter awaiting approval.
"""Add the due-time source for automatic approval."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261018_auto_approval_timestamp"
down_revision = "20261018_order_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("awaiting_approval_at", sa.DateTime(timezone=True)))
    # Recover existing delivery times where the durable event is available.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "UPDATE orders AS o SET awaiting_approval_at = delivery.delivered_at "
            "FROM (SELECT payload->>'order_id' AS order_id, "
            "MAX((payload->>'timestamp')::timestamptz) AS delivered_at "
            "FROM order_event_outbox WHERE payload->>'event_type' = 'OrderDelivered' "
            "GROUP BY payload->>'order_id') AS delivery "
            "WHERE o.order_id = delivery.order_id AND o.status = 'AWAITING_APPROVAL'"
        )
    # Without a delivery event, start the 24-hour clock at migration time.
    op.execute(
        "UPDATE orders SET awaiting_approval_at = CURRENT_TIMESTAMP "
        "WHERE status = 'AWAITING_APPROVAL' AND awaiting_approval_at IS NULL"
    )
    op.create_index(
        "ix_orders_awaiting_approval_at",
        "orders",
        ["awaiting_approval_at", "order_id"],
        postgresql_where=sa.text("status = 'AWAITING_APPROVAL'"),
        sqlite_where=sa.text("status = 'AWAITING_APPROVAL'"),
    )


def downgrade() -> None:
    op.drop_index("ix_orders_awaiting_approval_at", table_name="orders")
    op.drop_column("orders", "awaiting_approval_at")
