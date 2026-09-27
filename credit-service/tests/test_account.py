# AI-influenced: implemented with AI assistance; see ai/usage-log.md.
from __future__ import annotations

import pytest

from app.errors import NotFoundError
from app.models.transaction import TransactionKind
from app.services.credit_service import CreditService


async def test_ensure_account_allocates_initial_balance(session):
    service = CreditService(session)
    account = await service.ensure_account("user-1")
    assert account.available_balance == 100
    assert account.reserved_balance == 0
    transactions = await service.list_transactions("user-1")
    assert len(transactions) == 1
    assert transactions[0].kind == TransactionKind.ALLOCATION.value
    assert transactions[0].amount == 100


async def test_ensure_account_is_idempotent(session):
    service = CreditService(session)
    await service.ensure_account("user-1")
    await service.ensure_account("user-1")
    account = await service.get_balances("user-1")
    assert account.available_balance == 100
    transactions = await service.list_transactions("user-1")
    assert len(transactions) == 1  # no second allocation


async def test_get_balances_unknown_user_raises_not_found(session):
    service = CreditService(session)
    with pytest.raises(NotFoundError):
        await service.get_balances("ghost")


async def test_ensure_account_concurrent_race_is_idempotent(session, monkeypatch):
    """Simulates two concurrent UserRegistered deliveries: the first check
    sees no account, but another worker inserted it before our flush, so the
    primary-key constraint fires and we must fall back to the existing row."""
    service = CreditService(session)
    await service.ensure_account("user-1")  # the "other worker" wins first

    original_get = service._accounts.get
    state = {"calls": 0}

    async def _race_get(user_id):
        if state["calls"] == 0:
            state["calls"] += 1
            return None  # pretend the initial check ran before the other insert
        return await original_get(user_id)

    monkeypatch.setattr(service._accounts, "get", _race_get)
    account = await service.ensure_account("user-1")
    assert account.available_balance == 100
    transactions = await service.list_transactions("user-1")
    assert len(transactions) == 1  # no double allocation
