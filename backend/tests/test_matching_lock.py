"""Real PostgreSQL transaction-lock ordering and release with stable category keys."""
import asyncio
import os
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import create_async_engine

from library.matching_lock import MATCHING_LOCK_NAMESPACE, category_lock_key, lock_matching_categories


@pytest.fixture
def database_url():
    raw = os.getenv('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('TEST_DATABASE_URL is required')
    url = make_url(raw)
    if not url.database or not url.database.startswith('kaifind_test_'):
        raise RuntimeError('Lock tests require a separate test database')
    return url.set(drivername='postgresql+asyncpg')


def test_category_key_is_stable_and_signed():
    category = UUID('12345678-1234-5678-1234-567812345678')
    assert category_lock_key(category) == -573848482
    with pytest.raises(TypeError):
        category_lock_key(str(category))


def test_real_transaction_lock_is_held_and_released(database_url):
    async def run():
        engine = create_async_engine(database_url)
        category = uuid4()
        try:
            async with engine.connect() as owner, engine.connect() as observer:
                transaction = await owner.begin()
                await lock_matching_categories(owner, [category, category])
                statement = text('SELECT pg_try_advisory_xact_lock(:namespace, :category)')
                params = {'namespace': MATCHING_LOCK_NAMESPACE, 'category': category_lock_key(category)}
                assert await observer.scalar(statement, params) is False
                await transaction.rollback()
                assert await observer.scalar(statement, params) is True
                await observer.rollback()
                await owner.begin()
                await lock_matching_categories(owner, [category])
                assert await observer.scalar(statement, params) is False
                await owner.commit()
                assert await observer.scalar(statement, params) is True
                await observer.rollback()
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_opposite_category_orders_do_not_deadlock(database_url):
    async def run():
        engine = create_async_engine(database_url)
        categories = [uuid4(), uuid4()]

        async def writer(ids):
            async with engine.begin() as db:
                await db.execute(text("SET LOCAL lock_timeout = '2s'"))
                await lock_matching_categories(db, ids)

        try:
            await asyncio.wait_for(asyncio.gather(writer(categories), writer(reversed(categories))), timeout=5)
        finally:
            await engine.dispose()
    asyncio.run(run())


def test_missing_transaction_is_rejected(database_url):
    async def run():
        engine = create_async_engine(database_url)
        try:
            async with engine.connect() as db:
                with pytest.raises(RuntimeError):
                    await lock_matching_categories(db, [uuid4()])
        finally:
            await engine.dispose()
    asyncio.run(run())
