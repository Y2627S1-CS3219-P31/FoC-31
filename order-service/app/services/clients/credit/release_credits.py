# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from app.services.client_manager import get_credit_client


async def release_credits(
    reservation_id: str,
    requester_id: str,
):
    await get_credit_client().release_credits(
        reservation_id=reservation_id,
        requester_id=requester_id,
    )
