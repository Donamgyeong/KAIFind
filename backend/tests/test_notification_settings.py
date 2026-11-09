"""Deployment settings must fail explicitly instead of silently falling back."""

from dataclasses import replace
from datetime import time

import pytest

from library.notification_settings import NotificationSettings


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch):
    import os
    for key in os.environ:
        if key.startswith('NOTIFICATION_EMAIL_'):
            monkeypatch.delenv(key)


def test_defaults_and_overrides(monkeypatch):
    settings = NotificationSettings.from_environment()
    assert not settings.enabled
    assert settings.daily_limit == 20 and settings.digest_time == time(20)
    monkeypatch.setenv('NOTIFICATION_EMAIL_ENABLED', 'true')
    monkeypatch.setenv('NOTIFICATION_EMAIL_DAILY_LIMIT', '1')
    monkeypatch.setenv('NOTIFICATION_EMAIL_DIGEST_TIME', '00:00')
    monkeypatch.setenv('NOTIFICATION_EMAIL_APP_BASE_URL', 'https://kaifind.example')
    assert NotificationSettings.from_environment().daily_limit == 1
    assert NotificationSettings.from_environment().digest_time == time(0)


@pytest.mark.parametrize('key,value', [
    ('ENABLED', 'TRUE'), ('ENABLED', '1'), ('DAILY_LIMIT', '0'), ('DAILY_LIMIT', '-1'),
    ('DAILY_LIMIT', '1.5'), ('DIGEST_TIME', '24:00'), ('DIGEST_TIME', '9:00'),
    ('DIGEST_TIME', '20:00:00'), ('POLL_SECONDS', '0'), ('POLL_SECONDS', 'nan'),
    ('LEASE_SECONDS', '30'), ('TIMEOUT_SECONDS', 'inf'), ('RETRY_SECONDS', ''),
    ('RETRY_SECONDS', '60,0'), ('RETRY_SECONDS', '300,60'), ('MAX_ATTEMPTS', '0'),
    ('RETRY_JITTER_RATIO', 'nan'), ('RETRY_JITTER_RATIO', '1.1'), ('PROVIDER', 'smtp'),
])
def test_invalid_environment(monkeypatch, key, value):
    monkeypatch.setenv('NOTIFICATION_EMAIL_' + key, value)
    with pytest.raises(ValueError):
        NotificationSettings.from_environment()


@pytest.mark.parametrize('url', ['', 'http://example.com', 'https://user:pass@example.com',
                              'https://example.com/path', 'https://example.com?x=y'])
def test_enabled_requires_https_origin(url):
    with pytest.raises(ValueError):
        NotificationSettings(enabled=True, app_base_url=url)


def test_lifespan_starts_email_independently_of_analysis(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from main import lifespan

    started, closed = [], []

    class Worker:
        def __init__(self, *args):
            pass

        def start(self):
            started.append(True)

        async def close(self):
            closed.append(True)

    monkeypatch.setenv('NOTIFICATION_EMAIL_ENABLED', 'true')
    monkeypatch.setenv('NOTIFICATION_EMAIL_APP_BASE_URL', 'https://kaifind.example')
    monkeypatch.setattr('main.EmailWorker', Worker)
    monkeypatch.setattr('main.NotificationWorker', Worker)
    monkeypatch.setattr('main.session_factory', lambda: None)
    app = FastAPI(lifespan=lifespan)
    with TestClient(app):
        assert len(started) == 2
        assert app.state.text_analysis_state == 'DISABLED'
        assert app.state.notification_email_settings.enabled
    assert len(closed) == 2


def test_lifespan_rejects_invalid_email_settings(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from main import lifespan

    monkeypatch.setenv('NOTIFICATION_EMAIL_DAILY_LIMIT', '0')
    with pytest.raises(ValueError), TestClient(FastAPI(lifespan=lifespan)):
        pass
