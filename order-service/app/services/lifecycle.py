from __future__ import annotations

from enum import Enum


class OrderStatus(str, Enum):
    OPEN = "OPEN"
    ACCEPTED = "ACCEPTED"
    PICKED_UP = "PICKED_UP"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


ALLOWED_TRANSITIONS: dict[OrderStatus, set[OrderStatus]] = {
    OrderStatus.OPEN: {OrderStatus.ACCEPTED, OrderStatus.CANCELLED, OrderStatus.EXPIRED},
    OrderStatus.ACCEPTED: {OrderStatus.PICKED_UP, OrderStatus.OPEN, OrderStatus.CANCELLED},
    OrderStatus.PICKED_UP: {OrderStatus.AWAITING_APPROVAL},
    OrderStatus.AWAITING_APPROVAL: {OrderStatus.COMPLETED},
    OrderStatus.COMPLETED: set(),
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
}


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS.get(current, set())


def assert_transition(current: OrderStatus, target: OrderStatus) -> None:
    if not can_transition(current, target):
        raise ValueError(f"Invalid transition: {current.value} -> {target.value}")
