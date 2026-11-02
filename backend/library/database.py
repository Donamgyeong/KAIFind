"""Lazy async database access; importing the app never opens a DB connection."""
import os
from functools import lru_cache

from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


def database_url() -> URL:
    raw = os.getenv('DATABASE_URL')
    if raw:
        url = make_url(raw)
        if url.drivername not in ('postgres', 'postgresql', 'postgresql+asyncpg', 'postgresql+psycopg'):
            raise ValueError('KAIFind requires a PostgreSQL DATABASE_URL')
        return url.set(drivername='postgresql+asyncpg')
    required = ('POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_DB')
    if not all(os.getenv(key) for key in required):
        raise RuntimeError('Set DATABASE_URL or POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB')
    return URL.create('postgresql+asyncpg', username=os.environ['POSTGRES_USER'],
                      password=os.environ['POSTGRES_PASSWORD'],
                      host=os.getenv('POSTGRES_HOST', 'localhost'),
                      port=int(os.getenv('POSTGRES_PORT', '5432')),
                      database=os.environ['POSTGRES_DB'])


@lru_cache
def session_factory():
    engine = create_async_engine(database_url(), pool_pre_ping=True)
    return async_sessionmaker(engine, expire_on_commit=False)


async def get_session():
    async with session_factory()() as session:
        yield session
