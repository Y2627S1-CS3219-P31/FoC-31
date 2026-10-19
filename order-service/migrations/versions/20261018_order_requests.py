# AI-INFLUENCED: Add durable Order Service request results for idempotency.
"""Store successful Order Service request results."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261018_order_requests"
down_revision = "20261017_order_approval_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_requests",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("order_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("order_requests")
