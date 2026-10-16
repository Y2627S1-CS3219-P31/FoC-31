# AI-INFLUENCED: Consolidate order event delivery into one durable outbox with Codex.
"""Use one outbox for all Order Service event publication."""

from __future__ import annotations

import json
import uuid
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision = "20261016_single_order_event_outbox"
down_revision = "20261016_order_release_outbox"
branch_labels = None
depends_on = None

RELEASE_TABLE = "order_release_outbox"
RELEASE_TASKS_TABLE = "order_release_tasks"
UPDATE_TABLE = "order_update_outbox"
UPDATE_TASKS_TABLE = "order_update_tasks"
EVENT_TABLE = "order_event_outbox"


def _timestamp(value: datetime | str) -> str:
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _copy_pending_events(
    table_name: str, event_type_by_action: dict[str, str] | None = None
) -> None:
    connection = op.get_bind()
    tables = set(sa.inspect(connection).get_table_names())
    if table_name not in tables or EVENT_TABLE not in tables:
        return

    source = sa.Table(table_name, sa.MetaData(), autoload_with=connection)
    event_table = sa.Table(EVENT_TABLE, sa.MetaData(), autoload_with=connection)
    columns = set(source.c.keys())
    query = sa.select(source).where(source.c.status == "pending")
    if "published_at" in columns:
        query = query.where(source.c.published_at.is_(None))

    for row in connection.execute(query).mappings():
        values = dict(row)
        if event_type_by_action is not None:
            event_type = event_type_by_action.get(values["action"])
            if event_type is None:
                continue
            payload = {
                "event_type": event_type,
                "task_id": values["task_id"],
                "order_id": values["order_id"],
                "reservation_id": values["reservation_id"],
                "requester_id": values["requester_id"],
                "timestamp": _timestamp(values["created_at"]),
                "reason": values.get("reason"),
            }
            event_key = f"order-action:{values['task_id']}"
        else:
            proposed_order = values["proposed_order"]
            if isinstance(proposed_order, str):
                proposed_order = json.loads(proposed_order)
            payload = {
                "event_type": "OrderUpdate",
                "task_id": values["task_id"],
                "order_id": values["order_id"],
                "reservation_id": values["reservation_id"],
                "requester_id": values["requester_id"],
                "reward": proposed_order["reward"],
                "timestamp": _timestamp(values["created_at"]),
            }
            event_key = f"order-update:{values['task_id']}"

        event_id = str(uuid.uuid5(uuid.NAMESPACE_URL, event_key))
        already_copied = connection.execute(
            sa.select(event_table.c.event_id).where(event_table.c.event_id == event_id)
        ).first()
        if already_copied is None:
            connection.execute(event_table.insert().values(event_id=event_id, payload=payload))


def _rename_and_trim(old_name: str, new_name: str) -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if old_name not in tables or new_name in tables:
        return

    _copy_pending_events(
        old_name,
        {
            "delete": "OrderDeletionRequested",
            "cancel": "OrderCancellationRequested",
            "expire": "OrderExpiryRequested",
        }
        if old_name == RELEASE_TABLE
        else None,
    )
    op.rename_table(old_name, new_name)

    removable = {"published_at", "attempts"}
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(new_name)}
    removable.intersection_update(columns)
    if removable:
        with op.batch_alter_table(new_name) as batch:
            for column in sorted(removable):
                batch.drop_column(column)


def upgrade() -> None:
    _rename_and_trim(RELEASE_TABLE, RELEASE_TASKS_TABLE)
    _rename_and_trim(UPDATE_TABLE, UPDATE_TASKS_TABLE)


def _restore_publication_columns(table_name: str) -> None:
    if table_name not in sa.inspect(op.get_bind()).get_table_names():
        return
    columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table_name)}
    with op.batch_alter_table(table_name) as batch:
        if "published_at" not in columns:
            batch.add_column(sa.Column("published_at", sa.DateTime(timezone=True)))
        if "attempts" not in columns:
            batch.add_column(
                sa.Column("attempts", sa.Integer(), nullable=False, server_default="0")
            )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if RELEASE_TASKS_TABLE in tables and RELEASE_TABLE not in tables:
        _restore_publication_columns(RELEASE_TASKS_TABLE)
        op.rename_table(RELEASE_TASKS_TABLE, RELEASE_TABLE)
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if UPDATE_TASKS_TABLE in tables and UPDATE_TABLE not in tables:
        _restore_publication_columns(UPDATE_TASKS_TABLE)
        op.rename_table(UPDATE_TASKS_TABLE, UPDATE_TABLE)
