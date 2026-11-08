"""Auth integration fixtures use only a migrated disposable PostgreSQL database."""
import asyncio
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from service.auth import AuthRuntime, AuthSettings


@pytest.fixture(autouse=True)
def disable_model_in_http_tests(monkeypatch):
    # Real-model tests construct the runtime explicitly. Ordinary API tests must
    # remain runnable without model assets or heavy startup per TestClient.
    monkeypatch.setenv('TEXT_ANALYSIS_ENABLED', 'false')


class Clock:
    def __init__(self):
        self.now = datetime(2026, 11, 3, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now

    def advance(self, **kwargs):
        self.now += timedelta(**kwargs)


@pytest.fixture
def auth_runtime():
    raw = os.getenv('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('TEST_DATABASE_URL is required for Auth PostgreSQL integration tests')
    url = make_url(raw)
    if not url.database or not url.database.startswith('kaifind_test_'):
        raise RuntimeError('Auth tests require a disposable kaifind_test_* database')
    sync_engine = create_engine(url.set(drivername='postgresql+psycopg'), poolclass=NullPool)
    with sync_engine.begin() as db:
        db.execute(text('TRUNCATE users, sessions, auth_login_rates CASCADE'))
    engine = create_async_engine(url.set(drivername='postgresql+asyncpg'), poolclass=NullPool)
    rt = AuthRuntime(AuthSettings(environment='test', mock_enabled=True,
        encryption_key=b'test-key-not-for-production-1234', allowed_origins=('https://testserver',)),
        factory=async_sessionmaker(engine, expire_on_commit=False), clock=Clock())
    rt.sync_engine = sync_engine
    yield rt
    asyncio.run(engine.dispose())
    sync_engine.dispose()
