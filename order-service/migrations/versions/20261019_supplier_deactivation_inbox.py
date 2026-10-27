# AI-INFLUENCED: Add idempotent SupplierDeactivated consumption with Codex.
"""Remember processed SupplierDeactivated events."""

import sqlalchemy as sa
from alembic import op

revision = "20261019_supplier_deactivation_inbox"
down_revision = "20261018_remove_update_rejection_code"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "supplier_deactivation_inbox" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "supplier_deactivation_inbox",
        sa.Column("event_id", sa.String(36), primary_key=True),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade() -> None:
    op.drop_table("supplier_deactivation_inbox")
