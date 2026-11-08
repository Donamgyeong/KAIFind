"""Transaction-scoped category locks shared by writers, matching and collection.

Acquire before item/report row locks. When a category changes while locating the
row, roll back the whole transaction and reacquire both categories in key order.
The caller owns the transaction; these helpers never commit or start one.
"""
from collections.abc import Iterable
import hashlib
from uuid import UUID

from sqlalchemy import text


# PostgreSQL's two-int advisory-lock key space is separate from the role bigint lock.
MATCHING_LOCK_NAMESPACE = 0x4B414946


def category_lock_key(category_id: UUID) -> int:
    if not isinstance(category_id, UUID):
        raise TypeError('category_id must be a UUID')

    digest = hashlib.sha256(category_id.bytes).digest()
    return int.from_bytes(digest[:4], byteorder='big', signed=True)


async def lock_matching_categories(db, category_ids: Iterable[UUID]) -> None:
    keys = sorted({category_lock_key(category_id) for category_id in category_ids})
    if not db.in_transaction():
        raise RuntimeError('Category locks require a caller-owned transaction')

    for key in keys:
        await db.execute(
            text('SELECT pg_advisory_xact_lock(:namespace, :category)'),
            {'namespace': MATCHING_LOCK_NAMESPACE, 'category': key},
        )
