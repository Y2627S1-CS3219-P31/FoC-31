from __future__ import annotations


class RouteNotFoundError(Exception):
    pass


class MissingBearerTokenError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


class UpstreamServiceError(Exception):
    pass
