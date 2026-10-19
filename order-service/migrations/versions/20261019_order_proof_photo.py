# AI-INFLUENCED: Add the Order Service's proof-of-delivery photo reference.
"""Store the private S3 key for an order's proof-of-delivery photo."""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20261019_order_proof_photo"
down_revision = "20261018_auto_approval_timestamp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("proof_of_delivery_photo_key", sa.String(255)))


def downgrade() -> None:
    op.drop_column("orders", "proof_of_delivery_photo_key")
