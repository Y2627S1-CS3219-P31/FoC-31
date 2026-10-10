class RemoteServiceError(Exception):
    """Base error raised while communicating with another microservice."""

    def __init__(
        self,
        message: str,
        *,
        service_name: str | None = None,
        status_code: int | None = None,
        code: str | None = None
    ):
        super().__init__(message)
        self.service_name = service_name
        self.status_code = status_code
        self.code = code

class RemoteServiceUnavailableError(RemoteServiceError):
    """The remote service could not provide a usable response right now."""

class RemoteServiceContractError(RemoteServiceError):
    """The remote service response violated its documented API contract."""

class UnexpectedRemoteResponseError(RemoteServiceError):
    """The response was valid JSON, but its status/code was not expected."""