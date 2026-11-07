# AI-INFLUENCED: Reusable image validation and private S3 storage implemented with Codex.
"""Validate image bytes and store them in a caller-configured private bucket."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

import boto3
from botocore.config import Config
from PIL import Image, UnidentifiedImageError

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
IMAGE_FORMATS = {
    "JPEG": ("image/jpeg", "jpg"),
    "PNG": ("image/png", "png"),
    "WEBP": ("image/webp", "webp"),
}


class InvalidImageError(ValueError):
    """The supplied bytes are not a supported image."""


class ImageStorageError(Exception):
    """An image could not be stored or retrieved."""


@dataclass(frozen=True)
class ImageData:
    data: bytes
    content_type: str


def validate_image(data: bytes, claimed_type: str | None) -> ImageData:
    if not data:
        raise InvalidImageError("A non-empty photo is required.")
    if len(data) > MAX_IMAGE_BYTES:
        raise InvalidImageError("The photo must be 5 MiB or smaller.")
    if claimed_type not in {item[0] for item in IMAGE_FORMATS.values()}:
        raise InvalidImageError("Only JPEG, PNG, or WebP photos are supported.")
    try:
        with Image.open(BytesIO(data), formats=list(IMAGE_FORMATS)) as image:
            if image.width * image.height > MAX_IMAGE_PIXELS:
                raise InvalidImageError("The photo dimensions are too large.")
            actual_type = IMAGE_FORMATS[image.format][0]
            if actual_type != claimed_type:
                raise InvalidImageError("The photo type does not match its contents.")
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise InvalidImageError("The photo is not a valid image.") from exc
    return ImageData(data, claimed_type)


class PrivateImageStore:
    def __init__(self, bucket: str, region: str):
        self.bucket = bucket
        self.region = region
        self._client = None

    def _s3(self):
        if not self.bucket:
            raise ImageStorageError("Image bucket is not configured.")
        if self._client is None:
            self._client = boto3.client(
                "s3",
                region_name=self.region,
                config=Config(connect_timeout=3, read_timeout=8, retries={"max_attempts": 2}),
            )
        return self._client

    async def upload(self, prefix: str, image: ImageData) -> str:
        extension = next(ext for mime, ext in IMAGE_FORMATS.values() if mime == image.content_type)
        key = f"{prefix}/{uuid4().hex}.{extension}"
        try:
            await asyncio.to_thread(
                self._s3().put_object,
                Bucket=self.bucket,
                Key=key,
                Body=image.data,
                ContentType=image.content_type,
            )
        except Exception as exc:
            raise ImageStorageError("Image upload failed.") from exc
        return key

    async def get(self, key: str) -> ImageData:
        def read_object() -> ImageData:
            response = self._s3().get_object(Bucket=self.bucket, Key=key)
            body = response["Body"]
            try:
                data = body.read(MAX_IMAGE_BYTES + 1)
            finally:
                body.close()
            content_type = response.get("ContentType")
            if (
                not data
                or len(data) > MAX_IMAGE_BYTES
                or content_type not in {item[0] for item in IMAGE_FORMATS.values()}
            ):
                raise ImageStorageError("Stored image is invalid.")
            return ImageData(data, content_type)

        try:
            return await asyncio.to_thread(read_object)
        except ImageStorageError:
            raise
        except Exception as exc:
            raise ImageStorageError("Image retrieval failed.") from exc

    async def delete(self, key: str) -> None:
        try:
            await asyncio.to_thread(self._s3().delete_object, Bucket=self.bucket, Key=key)
        except Exception as exc:
            raise ImageStorageError("Image deletion failed.") from exc
