# AI-INFLUENCED: Verify shared image validation, private storage, and photo migration with Codex.
from __future__ import annotations

import importlib.util
from io import BytesIO
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from PIL import Image
from sqlalchemy import create_engine, inspect, text

from foc_shared.images import (
    ImageStorageError,
    InvalidImageError,
    PrivateImageStore,
    validate_image,
)


def _png() -> bytes:
    output = BytesIO()
    Image.new("RGB", (2, 2), "red").save(output, format="PNG")
    return output.getvalue()


def test_image_validation_checks_actual_format_and_claimed_type():
    photo = validate_image(_png(), "image/png")
    assert photo.content_type == "image/png"
    with pytest.raises(InvalidImageError, match="does not match"):
        validate_image(_png(), "image/jpeg")
    with pytest.raises(InvalidImageError, match="not a valid image"):
        validate_image(b"not an image", "image/png")


async def test_private_storage_upload_read_and_delete():
    stored = {}

    class FakeS3:
        def put_object(self, **kwargs):
            stored[kwargs["Key"]] = kwargs

        def get_object(self, **kwargs):
            item = stored[kwargs["Key"]]
            return {"Body": BytesIO(item["Body"]), "ContentType": item["ContentType"]}

        def delete_object(self, **kwargs):
            stored.pop(kwargs["Key"])

    store = PrivateImageStore("private-photos", "ap-southeast-1")
    store._client = FakeS3()
    photo = validate_image(_png(), "image/png")
    key = await store.upload("proof-of-delivery/order-1", photo)
    assert key.startswith("proof-of-delivery/order-1/")
    assert stored[key]["Bucket"] == "private-photos"
    assert await store.get(key) == photo
    await store.delete(key)
    assert stored == {}
    with pytest.raises(ImageStorageError):
        await PrivateImageStore("", "ap-southeast-1").upload("proof", photo)


def test_photo_key_migration_adds_nullable_column():
    path = Path(__file__).parents[1] / "migrations/versions/20261106_order_proof_photo.py"
    spec = importlib.util.spec_from_file_location("order_proof_photo_migration", path)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE orders (order_id VARCHAR PRIMARY KEY)"))
        migration.op = Operations(MigrationContext.configure(connection))
        migration.upgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("orders")}
        assert "proof_of_delivery_photo_key" in columns
        connection.execute(text("INSERT INTO orders (order_id) VALUES ('order-1')"))
        assert (
            connection.execute(text("SELECT proof_of_delivery_photo_key FROM orders")).scalar_one()
            is None
        )
        migration.downgrade()
        columns = {column["name"] for column in inspect(connection).get_columns("orders")}
        assert "proof_of_delivery_photo_key" not in columns
    engine.dispose()
