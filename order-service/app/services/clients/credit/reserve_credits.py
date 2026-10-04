import httpx
import os

from app.services.client_manager import get_credit_client

from app.services.clients.credit.schemas import ReservationDetails

async def reserve_credits(
    reward: int, 
    requester_id: str,
    order_id: str
) -> ReservationDetails:
    return await get_credit_client().reserve_credits(
        reward=reward,
        requester_id=requester_id,
        order_id=order_id
    )
