# AI-INFLUENCED: Store and retrieve successful Order Service request results.
from __future__ import annotations

from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.order_requests import OrderRequest


async def lock_request_id(session: AsyncSession, request_id: str) -> None:
    # Serialize simultaneous uses of a key before checking or inserting its row.
    key = int.from_bytes(sha256(f"order-request:{request_id}".encode()).digest()[:8], signed=True)
    await session.execute(select(func.pg_advisory_xact_lock(key)))


async def get_request(session: AsyncSession, request_id: str) -> OrderRequest | None:
    return await session.get(OrderRequest, request_id)


async def save_request(
    session: AsyncSession,
    *,
    request_id: str,
    action: str,
    order_id: str,
    actor_id: str,
    response: dict,
) -> None:
    session.add(
        OrderRequest(
            request_id=request_id,
            action=action,
            order_id=order_id,
            actor_id=actor_id,
            response=response,
        )
    )
    await session.flush()
