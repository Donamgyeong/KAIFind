"""Photo transactions, permission checks, and recoverable private object writes."""

import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from datetime import timedelta
from functools import lru_cache
from typing import Callable
from urllib.parse import urlsplit
from uuid import uuid4

from sqlalchemy import select, text
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.formparsers import MultiPartException, MultiPartParser

from library.photo_images import sanitize_image
from library.photo_storage import photo_storage
from library.protected_http import ROLE_LOCK
from model import (
    Category,
    DropOffVersion,
    FoundItem,
    Photo,
    PhotoAccessGrant,
    PhotoAttachment,
    PhotoUploadIntent,
    User,
)
from schema.photos import PhotoPurpose, PhotoUploadResponse
from service.audit import append_audit
from service.auth import AuthError, AuthService, COOKIE, IDLE, runtime, token_hash


@dataclass(frozen=True)
class PhotoSettings:
    max_bytes: int = 10 * 1024 * 1024
    max_pixels: int = 24_000_000
    unattached_seconds: int = 86400
    link_seconds: int = 60
    public_base_url: str = 'https://localhost:8000'

    def __post_init__(self):
        if min(self.max_bytes, self.max_pixels, self.unattached_seconds, self.link_seconds) <= 0:
            raise ValueError('Photo limits must be positive')

        parsed = urlsplit(self.public_base_url)
        if (
            parsed.scheme not in {'https', 'http'}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or parsed.path not in ('', '/')
        ):
            raise ValueError('PHOTO_PUBLIC_BASE_URL must be a service origin')
        if parsed.scheme != 'https' and parsed.hostname not in {'localhost', '127.0.0.1', '::1'}:
            raise ValueError('PHOTO_PUBLIC_BASE_URL requires HTTPS outside localhost')


@lru_cache
def settings():
    return PhotoSettings(
        max_bytes=int(os.getenv('PHOTO_MAX_BYTES', str(10 * 1024 * 1024))),
        max_pixels=int(os.getenv('PHOTO_MAX_PIXELS', '24000000')),
        unattached_seconds=int(os.getenv('PHOTO_UNATTACHED_SECONDS', '86400')),
        link_seconds=int(os.getenv('PHOTO_LINK_SECONDS', '60')),
        public_base_url=os.getenv('PHOTO_PUBLIC_BASE_URL', 'https://localhost:8000'),
    )


@dataclass
class PhotoRuntime:
    settings: PhotoSettings = field(default_factory=settings)
    storage_factory: Callable = photo_storage


def photo_runtime(request):
    configured = getattr(request.app.state, 'photo_runtime', None)
    return configured if configured is not None else PhotoRuntime()


class PhotoMultipartParser(MultiPartParser):
    complete = False

    def on_end(self):
        self.complete = True


async def parse_upload(request, config):
    """Bound chunked bodies too; keep all original bytes in memory, never disk."""
    limit = config.max_bytes + 64 * 1024
    length = request.headers.get('content-length')

    if length is not None:
        try:
            declared = int(length)
            if declared < 0:
                raise ValueError
        except ValueError:
            raise AuthError(400, 'VALIDATION_ERROR') from None
        if declared > limit:
            raise AuthError(413, 'PHOTO_TOO_LARGE')

    if request.headers.get('content-type', '').split(';')[0].strip().lower() != 'multipart/form-data':
        raise AuthError(415, 'PHOTO_MULTIPART_REQUIRED')

    too_large = False

    async def bounded():
        nonlocal too_large
        size = 0

        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                too_large = True
                raise MultiPartException('Request too large')
            yield chunk

    parser = PhotoMultipartParser(
        request.headers,
        bounded(),
        max_files=1,
        max_fields=1,
        max_part_size=1024,
    )
    parser.spool_max_size = limit

    try:
        form = await parser.parse()
    except Exception:
        # Some parser errors are not MultiPartException; close every partial file.
        for partial in parser._files_to_close_on_error:
            partial.close()
        raise AuthError(
            413 if too_large else 400,
            'PHOTO_TOO_LARGE' if too_large else 'VALIDATION_ERROR',
        ) from None

    try:
        if not parser.complete:
            raise AuthError(400, 'VALIDATION_ERROR')
        if sorted(k for k, _ in form.multi_items()) != ['file', 'purpose']:
            raise AuthError(400, 'VALIDATION_ERROR')

        upload, purpose = form['file'], form['purpose']
        if not isinstance(upload, UploadFile) or purpose not in {p.value for p in PhotoPurpose}:
            raise AuthError(400, 'VALIDATION_ERROR')

        content = await upload.read(config.max_bytes + 1)
        if len(content) > config.max_bytes:
            raise AuthError(413, 'PHOTO_TOO_LARGE')

        return content, purpose
    finally:
        await form.close()


class PhotoService:
    def __init__(self, auth_runtime, photos_runtime):
        self.rt, self.prt = auth_runtime, photos_runtime
        self.config = photos_runtime.settings

    async def authenticate(self, db, request, *, member=False, writing=False):
        await db.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'), {'key': ROLE_LOCK})

        auth = AuthService(self.rt)
        session = await auth.lookup(db, request.cookies.get(COOKIE))
        now = self.rt.clock()

        if session is not None and auth.expired(session, now):
            raise AuthError(401, 'SESSION_EXPIRED', clear_cookie=True)

        user = await db.get(User, session.user_id) if session is not None and session.user_id else None
        if member and user is None:
            raise AuthError(401, 'AUTH_REQUIRED')

        if writing:
            origin = request.headers.get('origin')
            if origin is not None and origin not in self.rt.settings.allowed_origins:
                raise AuthError(403, 'ORIGIN_NOT_ALLOWED')
            auth.require_csrf(session, request.headers.get('x-csrf-token'), now)

        if session is not None:
            session.last_activity_at = now
            session.idle_expires_at = min(now + IDLE, session.absolute_expires_at)

        return session, user, now

    async def upload(self, request):
        key = None
        storage = None

        try:
            async with self.rt.factory() as db, db.begin():
                _, user, now = await self.authenticate(db, request, member=True, writing=True)

                content, purpose = await parse_upload(request, self.config)
                image = await run_in_threadpool(
                    sanitize_image,
                    content,
                    self.config.max_bytes,
                    self.config.max_pixels,
                )
                del content

                extension = {'image/jpeg': 'jpg', 'image/png': 'png', 'image/webp': 'webp'}[image.content_type]
                key = f'photos/{uuid4().hex}.{extension}'

                # Commit the intent independently before any external write. A crash
                # or failed compensation leaves a durable key for scheduled recovery.
                async with self.rt.factory() as intents, intents.begin():
                    intents.add(
                        PhotoUploadIntent(
                            object_key=key,
                            cleanup_after=now + timedelta(hours=1),
                        )
                    )

                intent = await db.get(PhotoUploadIntent, key, with_for_update=True)
                if intent is None:
                    raise RuntimeError('Upload intent expired during upload')

                storage = self.prt.storage_factory()
                await run_in_threadpool(storage.put_sanitized, image.content, image.content_type, key)

                photo = Photo(
                    id=uuid4(),
                    uploader_id=user.id,
                    purpose=purpose,
                    object_key=key,
                    content_type=image.content_type,
                    size_bytes=len(image.content),
                    width=image.width,
                    height=image.height,
                    created_at=now,
                    unattached_expires_at=now + timedelta(
                        seconds=self.config.unattached_seconds
                    ),
                )
                db.add(photo)
                await db.delete(intent)
                await db.flush()

                result = PhotoUploadResponse.model_validate(
                    dict(
                        photoId=photo.id,
                        purpose=purpose,
                        contentType=photo.content_type,
                        sizeBytes=photo.size_bytes,
                        width=photo.width,
                        height=photo.height,
                        unattachedExpiresAt=photo.unattached_expires_at,
                    )
                )

            return result
        except BaseException:
            # A failed COMMIT may have reached PostgreSQL. Never delete an object
            # referenced by a committed Photo; leave uncertain cases to recovery.
            if key is not None and storage is not None:
                try:
                    async with self.rt.factory() as recovery, recovery.begin():
                        intent = await recovery.get(PhotoUploadIntent, key, with_for_update=True)
                        exists = await recovery.scalar(select(Photo.id).where(Photo.object_key == key))

                        if intent is not None and exists is None:
                            await run_in_threadpool(storage.delete, key)
                            await recovery.delete(intent)
                except Exception:
                    logging.getLogger(__name__).error('Photo upload recovery deferred')

            raise

    async def authorize(self, db, photo_id, user, now):
        # Match DB lifecycle triggers: lock the item before its attachment/photo.
        # Reading a photo first with a share lock would deadlock against hide or
        # category updates, which lock the item then update protection labels.
        attachment = await db.get(PhotoAttachment, photo_id)
        item = None
        if attachment is not None:
            item = await db.scalar(
                select(FoundItem)
                .where(FoundItem.id == attachment.item_id)
                .with_for_update(read=True)
            )
            if item is None or item.deleted_at is not None:
                raise AuthError(404, 'NOT_FOUND')

        photo = await db.scalar(select(Photo).where(Photo.id == photo_id).with_for_update(read=True))
        if photo is None:
            raise AuthError(404, 'NOT_FOUND')

        attachment = await db.scalar(
            select(PhotoAttachment)
            .where(PhotoAttachment.photo_id == photo.id)
            .with_for_update(read=True)
            .execution_options(populate_existing=True)
        )
        if attachment is None:
            if photo.unattached_expires_at is None or now >= photo.unattached_expires_at:
                raise AuthError(404, 'NOT_FOUND')
            if user is None:
                raise AuthError(401, 'AUTH_REQUIRED')
            if user.id != photo.uploader_id:
                raise AuthError(403, 'PHOTO_FORBIDDEN')

            return photo, True, None, False

        if item is None:
            # An attachment appeared while acquiring the photo lock. Retry rather
            # than acquire item locks in the opposite order to lifecycle writers.
            raise AuthError(409, 'CONCURRENT_MODIFICATION')
        if item.hidden and (user is None or (user.id != item.finder_id and user.role != 'ADMIN')):
            raise AuthError(404, 'NOT_FOUND')

        category = await db.scalar(
            select(Category)
            .where(Category.id == item.category_id)
            .with_for_update(read=True)
        )
        version = (
            await db.scalar(
                select(DropOffVersion)
                .where(DropOffVersion.id == attachment.drop_off_version_id)
                .with_for_update(read=True)
            )
            if attachment.drop_off_version_id
            else None
        )

        sensitive = bool(
            attachment.sensitive_latched
            or category.sensitive
            or (version and version.sensitive_latched)
        )
        protected = sensitive or photo.purpose == 'DROP_OFF' or attachment.drop_off_version_id is not None

        if attachment.detached_at is not None and not protected:
            # Removed ordinary item photos are not part of the public gallery.
            if user is None or (user.id != photo.uploader_id and user.role != 'ADMIN'):
                raise AuthError(404, 'NOT_FOUND')
            protected = True

        if protected and user is None:
            raise AuthError(401, 'AUTH_REQUIRED')

        return photo, protected, item.id, sensitive

    async def issue_url(self, request, photo_id):
        async with self.rt.factory() as db, db.begin():
            session, user, now = await self.authenticate(db, request, writing=True)

            # No JSON is required, but unexpected bodies are rejected with a bound.
            async for chunk in request.stream():
                if chunk:
                    raise AuthError(400, 'VALIDATION_ERROR')

            photo, protected, item_id, sensitive = await self.authorize(db, photo_id, user, now)

            token = secrets.token_urlsafe(32)
            expires = now + timedelta(seconds=self.config.link_seconds)
            db.add(
                PhotoAccessGrant(
                    token_hash=token_hash(token),
                    photo_id=photo.id,
                    session_id=session.id,
                    requires_session=protected,
                    expires_at=expires,
                    created_at=now,
                )
            )

            if sensitive:
                append_audit(db, user, 'PHOTO_ACCESS_URL_ISSUED', 'FOUND_ITEM', item_id, now, photoId=photo.id)

            result = dict(
                url=f'{self.config.public_base_url.rstrip("/")}/api/v1/photo-access/{token}',
                expiresAt=expires,
                contentType=photo.content_type,
            )

        return result

    async def content(self, request, token):
        if not re.fullmatch(r'[A-Za-z0-9_-]{43}', token):
            raise AuthError(404, 'NOT_FOUND')

        async with self.rt.factory() as db, db.begin():
            session, user, now = await self.authenticate(db, request)
            grant = await db.scalar(select(PhotoAccessGrant).where(PhotoAccessGrant.token_hash == token_hash(token)))
            if grant is None:
                raise AuthError(404, 'NOT_FOUND')
            if now >= grant.expires_at:
                raise AuthError(410, 'PHOTO_LINK_EXPIRED')

            photo, protected, item_id, sensitive = await self.authorize(db, grant.photo_id, user, now)
            if protected or grant.requires_session:
                if session is None or user is None:
                    raise AuthError(401, 'AUTH_REQUIRED')
                if session.id != grant.session_id:
                    raise AuthError(403, 'PHOTO_FORBIDDEN')

            content = await run_in_threadpool(self.prt.storage_factory().read, photo.object_key)
            if len(content) != photo.size_bytes:
                raise RuntimeError('Stored photo size mismatch')

            if sensitive:
                append_audit(db, user, 'SENSITIVE_PHOTO_VIEWED', 'FOUND_ITEM', item_id, now, photoId=photo.id)
            mime = photo.content_type

        # No StreamingResponse: all bytes and the audit COMMIT must succeed before
        # returning a response, including on repeat reads of the same grant.
        return content, mime


def service(request):
    return PhotoService(runtime(request), photo_runtime(request))
