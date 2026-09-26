from __future__ import annotations

import pytest

from app.repositories.supplier_repo import SupplierRepository
from app.schemas.supplier import SupplierCreate, SupplierUpdate


async def _seed(repo: SupplierRepository) -> None:
    await repo.create(
        SupplierCreate(
            name="Anna's x Soup Union",
            category="Food",
            building="Central Library",
            location_description="Next to NUS Co-op",
        )
    )
    await repo.create(
        SupplierCreate(name="NUS Co-op", category="Shopping", building="Central Library")
    )
    await repo.create(SupplierCreate(name="Printer @ Com 2", category="Printing", building="Com 2"))


@pytest.fixture
def repo(session):
    return SupplierRepository(session)


async def test_create_assigns_id_and_active(repo):
    created = await repo.create(SupplierCreate(name="Cool Spot", category="Food", building="Com2"))
    assert created.id
    assert created.active is True
    assert created.name == "Cool Spot"


async def test_get_returns_none_when_missing(repo):
    assert await repo.get("nope") is None


async def test_get_returns_supplier(repo):
    created = await repo.create(SupplierCreate(name="Cool Spot", category="Food", building="Com2"))
    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.id == created.id


async def test_list_excludes_deactivated(repo):
    await _seed(repo)
    all_active = await repo.list(page=1, page_size=50)
    assert all_active.total == 3
    # deactivate one
    target = all_active.items[0]
    await repo.deactivate(target.id)
    after = await repo.list(page=1, page_size=50)
    assert after.total == 2
    assert all(s.active for s in after.items)


async def test_list_filter_by_category(repo):
    await _seed(repo)
    res = await repo.list(page=1, page_size=50, categories=["Shopping"])
    assert res.total == 1
    assert res.items[0].category.value == "Shopping"


async def test_list_filter_by_zone(repo):
    await _seed(repo)
    res = await repo.list(page=1, page_size=50, zone="Central Library")
    assert res.total == 2


async def test_list_keyword_search_case_insensitive(repo):
    await _seed(repo)
    res = await repo.list(page=1, page_size=50, q="soup")
    assert res.total == 1
    assert "Soup" in res.items[0].name


async def test_list_pagination(repo):
    await _seed(repo)
    page1 = await repo.list(page=1, page_size=2)
    assert page1.total == 3
    assert len(page1.items) == 2
    assert page1.page == 1
    assert page1.page_size == 2
    page2 = await repo.list(page=2, page_size=2)
    assert len(page2.items) == 1


async def test_update_partial(repo):
    created = await repo.create(SupplierCreate(name="Cool Spot", category="Food", building="Com2"))
    updated = await repo.update(created.id, SupplierUpdate(name="Cooler Spot"))
    assert updated is not None
    assert updated.name == "Cooler Spot"
    assert updated.building == "Com2"


async def test_update_missing_returns_none(repo):
    assert await repo.update("nope", SupplierUpdate(name="x")) is None


async def test_deactivate_missing_returns_none(repo):
    assert await repo.deactivate("nope") is None


async def test_deactivate_sets_active_false(repo):
    created = await repo.create(SupplierCreate(name="Cool Spot", category="Food", building="Com2"))
    deactivated = await repo.deactivate(created.id)
    assert deactivated is not None
    assert deactivated.active is False
