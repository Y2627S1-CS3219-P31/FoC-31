# AI-INFLUENCED: Adapt shared image storage to Order Service proof photos with Codex.
"""Order-specific upload validation, storage configuration, and error mapping."""

from __future__ import annotations

import asyncio

from fastapi import UploadFile

from app.config import settings
from app.services.errors import InvalidOrderPhotoError, OrderPhotoStorageError
from foc_shared.images import (
    MAX_IMAGE_BYTES,
    ImageData,
    ImageStorageError,
    InvalidImageError,
    PrivateImageStore,
    validate_image,
)

Photo = ImageData
MAX_PHOTO_BYTES = MAX_IMAGE_BYTES


def _store() -> PrivateImageStore:
    return PrivateImageStore(settings.order_photo_bucket, settings.order_photo_region)


async def read_upload(upload: UploadFile) -> Photo:
    data = await upload.read(MAX_PHOTO_BYTES + 1)
    try:
        return await asyncio.to_thread(validate_image, data, upload.content_type)
    except InvalidImageError as exc:
        raise InvalidOrderPhotoError(str(exc)) from exc


async def upload(order_id: str, photo: Photo) -> str:
    try:
        return await _store().upload(f"proof-of-delivery/{order_id}", photo)
    except ImageStorageError as exc:
        raise OrderPhotoStorageError() from exc


async def get(key: str) -> Photo:
    try:
        return await _store().get(key)
    except ImageStorageError as exc:
        raise OrderPhotoStorageError() from exc


async def delete(key: str) -> None:
    try:
        await _store().delete(key)
    except ImageStorageError as exc:
        raise OrderPhotoStorageError() from exc
