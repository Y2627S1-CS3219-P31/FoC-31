# AI-INFLUENCED: Add publication state to the order update outbox with Codex.
"""Track whether a pending order amendment was published.

Revision ID: 20261016_update_outbox_dispatch
Revises:
"""

import sqlalchemy as sa
from alembic import op

revision = "20261016_update_outbox_dispatch"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "order_update_outbox" not in inspector.get_table_names():
        return  # Fresh databases get the complete table from create_all().
    columns = {column["name"] for column in inspector.get_columns("order_update_outbox")}
    if "credit_required" not in columns:
        op.add_column(
            "order_update_outbox",
            sa.Column("credit_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    if "published_at" not in columns:
        op.add_column("order_update_outbox", sa.Column("published_at", sa.DateTime(timezone=True)))


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "order_update_outbox" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("order_update_outbox")}
    if "published_at" in columns:
        op.drop_column("order_update_outbox", "published_at")
    if "credit_required" in columns:
        op.drop_column("order_update_outbox", "credit_required")
