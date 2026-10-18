# AI-INFLUENCED: Sprint 1 Order Service domain exceptions generated with Codex.


class OrderServiceError(Exception):
    """Base class for expected Order Service failures."""


class OrderAcceptanceError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to accept order '{order_id}'.")
        self.order_id = order_id


class OrderDeliveryError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to mark order '{order_id}' as delivered.")
        self.order_id = order_id


class OrderPickupError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to mark order '{order_id}' as picked up.")
        self.order_id = order_id


class OrderWithdrawalError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to withdraw from order '{order_id}'.")
        self.order_id = order_id


class OrderApprovalError(OrderServiceError):
    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to start approval of order '{order_id}'.")
        self.order_id = order_id


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


class OrderNotEditableError(OrderServiceError):
    """Raised when an order is no longer eligible for requester updates."""

    def __init__(self, order_id: str) -> None:
        super().__init__("Only an open order without an assigned courier can be updated.")
        self.order_id = order_id


class OrderUpdatePendingError(OrderServiceError):
    """The update remains durable and will be retried by the worker."""

    def __init__(self, order_id: str) -> None:
        super().__init__("The order update is still pending and will be retried.")
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
    """Raised when an order deletion task cannot be saved."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to start deletion of order '{order_id}'.")
        self.order_id = order_id


class OrderCancellationError(OrderServiceError):
    """Raised when an order cancellation task cannot be saved."""

    def __init__(self, order_id: str) -> None:
        super().__init__(f"Failed to start cancellation of order '{order_id}'.")
        self.order_id = order_id
