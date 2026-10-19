# AI-INFLUENCED: Validate and store private Order Service delivery photos.
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from functools import lru_cache
from io import BytesIO
from uuid import uuid4

import boto3
from botocore.config import Config
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError

from app.config import settings
from app.services.errors import InvalidOrderPhotoError, OrderPhotoStorageError

MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_PHOTO_PIXELS = 20_000_000
PHOTO_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


@dataclass(frozen=True)
class Photo:
    data: bytes
    content_type: str


def _validate_image(data: bytes, claimed_type: str | None) -> Photo:
    if not data:
        raise InvalidOrderPhotoError("A non-empty photo is required.")
    if len(data) > MAX_PHOTO_BYTES:
        raise InvalidOrderPhotoError("The photo must be 5 MiB or smaller.")
    if claimed_type not in {item[0] for item in PHOTO_FORMATS.values()}:
        raise InvalidOrderPhotoError("Only JPEG, PNG, or WebP photos are supported.")
    try:
        with Image.open(BytesIO(data), formats=list(PHOTO_FORMATS)) as image:
            if image.width * image.height > MAX_PHOTO_PIXELS:
                raise InvalidOrderPhotoError("The photo dimensions are too large.")
            actual_type = PHOTO_FORMATS[image.format][0]
            if actual_type != claimed_type:
                raise InvalidOrderPhotoError("The photo type does not match its contents.")
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidOrderPhotoError("The photo is not a valid image.") from exc
    return Photo(data, claimed_type)


async def read_upload(upload: UploadFile) -> Photo:
    data = await upload.read(MAX_PHOTO_BYTES + 1)
    return await asyncio.to_thread(_validate_image, data, upload.content_type)


@lru_cache(maxsize=1)
def _client():
    return boto3.client(
        "s3",
        region_name=settings.order_photo_region,
        config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 2}),
    )


def _bucket() -> str:
    if not settings.order_photo_bucket:
        raise OrderPhotoStorageError()
    return settings.order_photo_bucket


async def upload(order_id: str, photo: Photo) -> str:
    bucket = _bucket()
    extension = next(ext for mime, ext in PHOTO_FORMATS.values() if mime == photo.content_type)
    key = f"proof-of-delivery/{order_id}/{uuid4().hex}.{extension}"

    def write_object() -> None:
        _client().put_object(
            Bucket=bucket, Key=key, Body=photo.data, ContentType=photo.content_type
        )

    try:
        await asyncio.to_thread(write_object)
    except Exception as exc:
        raise OrderPhotoStorageError() from exc
    return key


async def get(key: str) -> Photo:
    bucket = _bucket()

    def read_object() -> Photo:
        response = _client().get_object(Bucket=bucket, Key=key)
        body = response["Body"]
        try:
            data = body.read(MAX_PHOTO_BYTES + 1)
        finally:
            body.close()
        if (
            not data
            or len(data) > MAX_PHOTO_BYTES
            or response.get("ContentType") not in {item[0] for item in PHOTO_FORMATS.values()}
        ):
            raise OrderPhotoStorageError()
        return Photo(data, response["ContentType"])

    try:
        return await asyncio.to_thread(read_object)
    except OrderPhotoStorageError:
        raise
    except Exception as exc:
        raise OrderPhotoStorageError() from exc


async def delete(key: str) -> None:
    try:
        await asyncio.to_thread(lambda: _client().delete_object(Bucket=_bucket(), Key=key))
    except Exception as exc:
        raise OrderPhotoStorageError() from exc
