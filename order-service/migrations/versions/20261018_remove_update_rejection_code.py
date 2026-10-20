# AI-INFLUENCED: Remove unused order update rejection codes with Codex.
"""Drop the unused rejection code from order update tasks."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261018_remove_update_rejection_code"
down_revision = "20261018_auto_approval_timestamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("order_update_tasks") as batch:
        batch.drop_column("rejection_code")


def downgrade() -> None:
    with op.batch_alter_table("order_update_tasks") as batch:
        batch.add_column(sa.Column("rejection_code", sa.String(60), nullable=True))
