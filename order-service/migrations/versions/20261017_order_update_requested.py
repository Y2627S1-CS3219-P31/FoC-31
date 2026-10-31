# AI-INFLUENCED: Rename pending update outbox events with Codex.
"""Rename unpublished OrderUpdate events to OrderUpdateRequested."""

from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "20261017_order_update_requested"
down_revision = "20261017_order_expiry_index"
branch_labels = None
depends_on = None

EVENT_TABLE = "order_event_outbox"


def _rename_pending_events(old_type: str, new_type: str) -> None:
    connection = op.get_bind()
    if EVENT_TABLE not in sa.inspect(connection).get_table_names():
        return

    event_table = sa.Table(EVENT_TABLE, sa.MetaData(), autoload_with=connection)
    rows = connection.execute(
        sa.select(event_table.c.event_id, event_table.c.payload).where(
            event_table.c.published_at.is_(None)
        )
    )
    for event_id, stored_payload in rows:
        payload = json.loads(stored_payload) if isinstance(stored_payload, str) else stored_payload
        if payload.get("event_type") != old_type:
            continue
        payload["event_type"] = new_type
        connection.execute(
            event_table.update().where(event_table.c.event_id == event_id).values(payload=payload)
        )


def upgrade() -> None:
    _rename_pending_events("OrderUpdate", "OrderUpdateRequested")


def downgrade() -> None:
    _rename_pending_events("OrderUpdateRequested", "OrderUpdate")
