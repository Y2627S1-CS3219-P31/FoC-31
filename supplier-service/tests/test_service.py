from __future__ import annotations

import pytest

from app.errors import ConflictError, NotFoundError
from app.repositories.supplier_repo import SupplierRepository
from app.schemas.supplier import SupplierCreate, SupplierUpdate
from app.services.supplier_service import SupplierService


@pytest.fixture
def service(session):
    return SupplierService(SupplierRepository(session))


async def test_get_raises_not_found(service):
    with pytest.raises(NotFoundError):
        await service.get("missing")


async def test_create_then_get(service):
    created = await service.create(
        SupplierCreate(name="Cool Spot", category="Food", building="Com2")
    )
    fetched = await service.get(created.id)
    assert fetched.id == created.id


async def test_update_missing_raises_not_found(service):
    with pytest.raises(NotFoundError):
        await service.update("missing", SupplierUpdate(name="x"))


async def test_deactivate_missing_raises_not_found(service):
    with pytest.raises(NotFoundError):
        await service.deactivate("missing")


async def test_deactivate_twice_raises_conflict(service):
    created = await service.create(
        SupplierCreate(name="Cool Spot", category="Food", building="Com2")
    )
    await service.deactivate(created.id)
    with pytest.raises(ConflictError):
        await service.deactivate(created.id)
