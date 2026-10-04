# AI-INFLUENCED: Sprint 1 Order Service domain exceptions generated with Codex.


class OrderServiceError(Exception):
    """Base class for expected Order Service failures."""


class OrderNotFoundError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Order '{order_id}' was not found.")
        self.order_id = order_id


class OrderAccessDeniedError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"You do not have permission to access order '{order_id}'.")
        self.order_id = order_id


class OrderStateConflictError(OrderServiceError):
    def __init__(self, order_id: str, message: str) -> None:
        super().__init__(message)
        self.order_id = order_id


class OrderPersistenceError(OrderServiceError):
    """Raised when a new order cannot be persisted to the database."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to persist order '{order_id}'.")
        self.order_id = order_id


class OrderRetrievalError(OrderServiceError):
    """Raised when orders cannot be read from the database."""

    def __init__(self, order_id: str | None = None) -> None:
        message = "Failed to retrieve orders from the database."
        if order_id is not None:
            message = f"Failed to retrieve order '{order_id}' from the database."
        super().__init__(message)
        self.order_id = order_id


class OrderDeletionError(OrderServiceError):
    """Raised when an order cannot be deleted from the database."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to delete order '{order_id}' from the database.")
        self.order_id = order_id
