# AI-INFLUENCED: CI lint fixes applied with Codex; see ai/usage-log.md.
from dataclasses import dataclass
from typing import Any

import httpx

from app.services.clients.errors import (
    RemoteServiceContractError,
    RemoteServiceUnavailableError,
)


@dataclass(frozen=True)
class JsonResponse:
    status_code: int
    payload: dict[str, Any]

class JsonHttpTransport:
    """Reusable HTTP mechanics. Knows no endpoint semantics"""

    def __init__(self, client):
        self._client = client

    async def request(
        self,
        *,
        service_name,
        method,
        url,
        **request_options: Any
    ):
        # Check for connection issues
        try:
            response = await self._client.request(
                method,
                url,
                **request_options
            )
        except httpx.TimeoutException as exc: 
            raise RemoteServiceUnavailableError(
                f"Connection to {service_name} service timed out",
                service_name=service_name
            ) from exc
        except httpx.RequestError as exc:
            raise RemoteServiceUnavailableError(
                f"Could not communicate with {service_name}",
                service_name=service_name
            ) from exc

        # Check for rate limiting or server side issues
        # (without endpoint specific knowledge)
        if response.status_code == 429 or response.status_code >= 500:
            raise RemoteServiceUnavailableError(
                f"{service_name} returned {response.status_code}",
                service_name=service_name,
                status_code=response.status_code
            )

        # Check for parsability
        try: 
            payload = response.json()
        except ValueError as exc:
            raise RemoteServiceContractError(
                f"{service_name} did not return valid JSON",
                service_name=service_name,
                status_code=response.status_code
            ) from exc

        # Check that payload is a dict object (common check for
        # all endpoints)
        if not isinstance(payload, dict):
            raise RemoteServiceContractError(
                f"{service_name} returned a non-object JSON"
                f" response",
                service_name=service_name,
                status_code=response.status_code
            )

        # Return payload to caller wrapped in JsonResponse object
        # so higher layers don't depend directly on HTTPX and
        # the payload is encapsulated with its status code
        # without needing to be parsed again
        # Further service-specific checks will be done by the
        # higher layers
        return JsonResponse(
            status_code=response.status_code,
            payload=payload
        )
