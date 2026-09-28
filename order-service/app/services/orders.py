# AI-influenced: implemented with Codex; see ai/usage-log.md.
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients import credits as credit_client_module
from app.clients import suppliers as supplier_client_module
from app.clients.credits import CreditClient
from app.clients.suppliers import SupplierClient
from app.models.orders import Order
from app.repositories import orders as order_repository
from app.schemas.orders import OrderCreate
from app.services.lifecycle import OrderStatus


class OrderNotFoundError(Exception):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"Order '{order_id}' was not found.")


class OrderAccessDeniedError(Exception):
    def __init__(self, order_id: int) -> None:
        self.order_id = order_id
        super().__init__(f"You do not have permission to access order '{order_id}'.")


class OrderStateConflictError(Exception):
    def __init__(self, order_id: int, message: str) -> None:
        self.order_id = order_id
        super().__init__(message)


class SupplierNotFoundError(Exception):
    pass


class SupplierInactiveError(Exception):
    pass


class DependencyUnavailableError(Exception):
    def __init__(self, dependency: str, message: str) -> None:
        self.dependency = dependency
        super().__init__(message)


class CreditReservationError(Exception):
    pass


async def create_order(
    session: AsyncSession,
    order_data: OrderCreate,
    requester_id: str,
    supplier_client: SupplierClient,
    credit_client: CreditClient,
) -> Order:
    try:
        supplier = await supplier_client.get_supplier(order_data.supplier_id)
    except supplier_client_module.SupplierNotFoundError as error:
        raise SupplierNotFoundError(str(error)) from error
    except supplier_client_module.SupplierServiceUnavailableError as error:
        raise DependencyUnavailableError("supplier", str(error)) from error

    if not supplier.active:
        raise SupplierInactiveError(f"Supplier '{order_data.supplier_id}' is deactivated.")

    try:
        database_order = await order_repository.stage_order(
            session,
            order_data,
            requester_id,
            OrderStatus.OPEN.value,
        )
        await credit_client.reserve(
            order_id=database_order.id,
            requester_id=requester_id,
            amount=order_data.reward,
        )
        await order_repository.commit_order(session)
    except credit_client_module.CreditReservationRejectedError as error:
        await session.rollback()
        raise CreditReservationError(str(error)) from error
    except credit_client_module.CreditServiceUnavailableError as error:
        await session.rollback()
        raise DependencyUnavailableError("credit", str(error)) from error
    except Exception:
        await session.rollback()
        raise

    return database_order


async def list_requester_orders(session: AsyncSession, requester_id: str) -> list[Order]:
    return await order_repository.list_orders_for_requester(session, requester_id)


async def get_order_for_requester(
    session: AsyncSession,
    order_id: int,
    requester_id: str,
) -> Order:
    order = await order_repository.get_order(session, order_id)
    if order is None:
        raise OrderNotFoundError(order_id)
    if order.requester_id != requester_id:
        raise OrderAccessDeniedError(order_id)
    return order


async def delete_order_for_requester(
    session: AsyncSession,
    order_id: int,
    requester_id: str,
) -> None:
    order = await get_order_for_requester(session, order_id, requester_id)
    if order.status != OrderStatus.OPEN.value:
        raise OrderStateConflictError(
            order_id,
            f"Order '{order_id}' can only be deleted while its status is 'OPEN'.",
        )
    if order.courier_id is not None:
        raise OrderStateConflictError(
            order_id,
            "An order with an assigned courier cannot be deleted.",
        )
    await order_repository.delete_order(session, order)
