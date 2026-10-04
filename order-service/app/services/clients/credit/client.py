from app.services.clients.client import JsonServiceClient
from app.services.clients.transport import JsonHttpTransport
from app.services.clients.credit.schemas import ReservationDetails
from app.services.clients.credit.error import (
    CreditAccountNotFoundError,
    InsufficientCreditsError,
    ReservationConflictError,
    ReservationForbiddenError,
    ReservationNotFoundError
)

class CreditClient(JsonServiceClient):
    def __init__(
        self,
        *,
        base_url: str,
        transport: JsonHttpTransport
    ):
        super().__init__(
            service_name="Credit Service",
            base_url=base_url.rstrip("/"),
            transport=transport
        )

    async def reserve_credits(
        self,
        reward: int,
        requester_id: str,
        order_id: str
    ) -> ReservationDetails:
        return await self._request_model(
            method="POST",
            path="/credits/reservations",
            expected_status=201,
            response_model=ReservationDetails,
            endpoint_errors={
                (404, "not_found"): CreditAccountNotFoundError,
                (409, "insufficient_credits"): InsufficientCreditsError,
                (409, "conflict"): ReservationConflictError,
            },
            # Header
            headers={
                "X-User-Id": requester_id
            },
            json={
                "user_id": requester_id,
                "order_id": order_id,
                "amount": reward
            }
        )

    async def release_credits(
        self,
        reservation_id: str,
        requester_id: str
    ):
        return await self._request_model(
            method="POST",
            path=f"/credits/reservations/{reservation_id}/release",
            expected_status=200,
            response_model=ReservationDetails,
            endpoint_errors={
                (404, "not_found"): ReservationNotFoundError,
                (403, "forbidden"): ReservationForbiddenError,
                (409, "conflict"): ReservationConflictError,
            },
            headers={
                "X-User-Id": requester_id
            }
        )   
