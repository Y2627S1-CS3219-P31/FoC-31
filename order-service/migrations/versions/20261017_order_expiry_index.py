# AI-INFLUENCED: Add an index for the batched order expiry sweep.
"""Index open orders by deadline for the expiry sweeper."""

import sqlalchemy as sa
from alembic import op

revision = "20261017_order_expiry_index"
down_revision = "20261016_single_order_event_outbox"
branch_labels = None
depends_on = None

INDEX_NAME = "ix_orders_open_deadline"


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "orders" not in inspector.get_table_names():
        return
    if any(index["name"] == INDEX_NAME for index in inspector.get_indexes("orders")):
        return

    op.create_index(
        INDEX_NAME,
        "orders",
        ["deadline", "order_id"],
        postgresql_where=sa.text("status = 'OPEN'"),
        sqlite_where=sa.text("status = 'OPEN'"),
    )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "orders" not in inspector.get_table_names():
        return
    if any(index["name"] == INDEX_NAME for index in inspector.get_indexes("orders")):
        op.drop_index(INDEX_NAME, table_name="orders")
