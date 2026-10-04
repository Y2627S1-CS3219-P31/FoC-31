from collections.abc import Mapping
from pydantic import BaseModel, ValidationError
from typing import Any, TypeVar

from foc_shared.errors import ErrorEnvelope
from app.services.clients.errors import (
    RemoteServiceContractError,
    UnexpectedRemoteResponseError
)
from app.services.clients.transport import JsonHttpTransport

# TypeVar is used for more specific typing of _request_model 
# return type
ResponseModel = TypeVar("ResponseModel", bound=BaseModel)

# Type alias for an error mapping
ErrorMap = Mapping[tuple[int, str], type[Exception]]

class JsonServiceClient():
    """Reusable contract validation with specific error mappings """

    def __init__(
        self,
        *,
        service_name: str,
        base_url: str,
        transport: JsonHttpTransport
    ):
        self._service_name = service_name
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    async def _request_model(
        self,
        *,
        method: str,
        path: str,
        expected_status: int,
        response_model: type[ResponseModel],
        endpoint_errors: ErrorMap | None = None,
        **request_options: Any # Any value for the dictionary items
    ) -> ResponseModel:
        # Use the reusable request call from JsonHttpTransport
        response = await self._transport.request(
            service_name=self._service_name,
            method=method,
            url=f"{self._base_url}{path}",
            **request_options
        )

        # Check if the response has the expected status code
        # of the endpoint
        if response.status_code == expected_status:
            try:
                return response_model.model_validate(
                    response.payload)
            except ValidationError as exc:
                raise RemoteServiceContractError(
                    f"{self._service_name} did not return the"
                    f" agreed payload shape"
                ) from exc

        # If response doesn't have expected status code,
        # check if the payload follows the error envelope 
        # shape first
        try:
            error = ErrorEnvelope.model_validate(response.payload)
        except ValidationError as exc:
            raise RemoteServiceContractError(
                f"{self._service_name} returned an invalid "
                f"error envelope."
            )

        # Get the correct exception type based on the status code and error code
        exception_type = (endpoint_errors or {}).get(
            (response.status_code, error.code)
        )
        if exception_type is not None:
            raise exception_type(error.message)

        # Raise unexpected error
        raise UnexpectedRemoteResponseError(
            message=error.message,
            service_name=self._service_name,
            status_code=response.status_code,
            code=error.code
        )
