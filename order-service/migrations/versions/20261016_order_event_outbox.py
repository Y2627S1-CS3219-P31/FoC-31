# AI-INFLUENCED: Durable order event outbox migration implemented with Codex.
"""Add durable lifecycle event publication."""

import sqlalchemy as sa
from alembic import op

revision = "20261016_order_event_outbox"
down_revision = "20261016_update_outbox_dispatch"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "order_event_outbox" in sa.inspect(op.get_bind()).get_table_names():
        return  # Startup may already have created this new table.
    op.create_table(
        "order_event_outbox",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_order_event_outbox_published_at", "order_event_outbox", ["published_at"])


def downgrade() -> None:
    op.drop_table("order_event_outbox")
