"""Scheduled, retryable cleanup: python -m service.photo_cleanup."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import delete, exists, select
from starlette.concurrency import run_in_threadpool

from library.database import session_factory
from library.photo_storage import photo_storage
from model import Photo, PhotoAccessGrant, PhotoAttachment, PhotoUploadIntent


async def cleanup(factory, storage, now, batch_size=100):
    counts = dict(intents=0, photos=0, grants=0, failures=0)

    async with factory() as db, db.begin():
        intents = (
            await db.scalars(
                select(PhotoUploadIntent)
                .where(PhotoUploadIntent.cleanup_after <= now)
                .order_by(PhotoUploadIntent.cleanup_after)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()

        for intent in intents:
            referenced = await db.scalar(select(Photo.id).where(Photo.object_key == intent.object_key))
            if referenced is None:
                try:
                    await run_in_threadpool(storage.delete, intent.object_key)
                except Exception:
                    counts['failures'] += 1
                    continue

            await db.delete(intent)
            counts['intents'] += 1

    async with factory() as db, db.begin():
        # The photo row lock is also required by attachment writers. A historical
        # attachment still owns its photo and must not be treated as unattached.
        photos = (
            await db.scalars(
                select(Photo)
                .where(
                    Photo.unattached_expires_at <= now,
                    ~exists().where(PhotoAttachment.photo_id == Photo.id),
                )
                .order_by(Photo.unattached_expires_at)
                .limit(batch_size)
                .with_for_update(skip_locked=True)
            )
        ).all()

        for photo in photos:
            try:
                await run_in_threadpool(storage.delete, photo.object_key)
            except Exception:
                counts['failures'] += 1
                continue

            await db.delete(photo)
            counts['photos'] += 1

    async with factory() as db, db.begin():
        ids = select(PhotoAccessGrant.id).where(PhotoAccessGrant.expires_at <= now).limit(batch_size)
        result = await db.execute(delete(PhotoAccessGrant).where(PhotoAccessGrant.id.in_(ids)))
        counts['grants'] = result.rowcount

    return counts


async def main():
    counts = await cleanup(session_factory(), photo_storage(), datetime.now(timezone.utc))

    print(counts)  # Counts only; object keys and tokens never enter logs.
    if counts['failures']:
        raise SystemExit(1)


if __name__ == '__main__':
    asyncio.run(main())
