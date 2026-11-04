"""Private MinIO photo storage. Call blocking methods from a worker thread.

Only the photo service's decoded, sanitized image bytes belong here. Access
authorization and EXIF removal must happen before calling this adapter.
"""

import os
from dataclasses import dataclass, field
from functools import lru_cache
from io import BytesIO
from uuid import uuid4

from minio import Minio
from urllib3 import PoolManager, Timeout


@dataclass(frozen=True)
class StorageSettings:
    endpoint: str
    access_key: str = field(repr=False)
    secret_key: str = field(repr=False)
    bucket: str = 'kaifind-photos'
    secure: bool = True

    @classmethod
    def from_env(cls):
        required = ('MINIO_ENDPOINT', 'MINIO_ACCESS_KEY', 'MINIO_SECRET_KEY')
        if not all(os.getenv(key, '').strip() for key in required):
            raise RuntimeError('Set MINIO_ENDPOINT, MINIO_ACCESS_KEY, MINIO_SECRET_KEY')

        secure = os.getenv('MINIO_SECURE', 'true').lower()
        if secure not in ('true', 'false'):
            raise ValueError('MINIO_SECURE must be true or false')

        bucket = os.getenv('MINIO_BUCKET', 'kaifind-photos').strip()
        if not bucket:
            raise ValueError('MINIO_BUCKET must not be empty')

        return cls(
            endpoint=os.environ['MINIO_ENDPOINT'],
            access_key=os.environ['MINIO_ACCESS_KEY'],
            secret_key=os.environ['MINIO_SECRET_KEY'],
            bucket=bucket,
            secure=secure == 'true',
        )


class PhotoStorage:
    def __init__(self, settings: StorageSettings, client: Minio | None = None):
        self.bucket = settings.bucket
        self.client = client if client is not None else Minio(
            settings.endpoint,
            access_key=settings.access_key,
            secret_key=settings.secret_key,
            secure=settings.secure,
            http_client=PoolManager(timeout=Timeout(connect=3, read=30), retries=1),
        )

    def put_sanitized(
        self,
        content: bytes,
        content_type: str,
        object_key: str | None = None,
    ) -> str:
        extensions = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}
        if not content or content_type not in extensions:
            raise ValueError('Expected nonempty sanitized JPEG, PNG or WebP bytes')

        key = object_key or f'photos/{uuid4().hex}.{extensions[content_type]}'

        self.client.put_object(
            self.bucket,
            key,
            BytesIO(content),
            len(content),
            content_type=content_type,
            # Each bounded photo fits in one PUT. This avoids
            # abandoned multipart parts after a process crash.
            part_size=max(5 * 1024 * 1024, len(content)),
        )

        return key

    def read(self, object_key: str) -> bytes:
        response = self.client.get_object(self.bucket, object_key)

        try:
            return response.read()
        finally:
            try:
                response.close()
            finally:
                response.release_conn()

    def delete(self, object_key: str) -> None:
        self.client.remove_object(self.bucket, object_key)


@lru_cache
def photo_storage() -> PhotoStorage:
    """Configure lazily; importing the app requires no storage credentials."""
    return PhotoStorage(StorageSettings.from_env())
