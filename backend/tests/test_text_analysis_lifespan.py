"""App startup explicitly distinguishes disabled, invalid and resident models."""
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from library.text_analysis_types import AnalysisError
from main import lifespan


def test_disabled_runtime_does_not_load_model():
    app = FastAPI(lifespan=lifespan)
    with TestClient(app):
        assert app.state.text_analysis_state == 'DISABLED'
        assert app.state.text_analysis_runtime is None


def test_enabled_runtime_fails_startup_if_assets_are_missing(monkeypatch, tmp_path):
    monkeypatch.setenv('TEXT_ANALYSIS_ENABLED', 'true')
    monkeypatch.setenv('TEXT_ANALYSIS_MODEL_DIR', str(tmp_path))
    app = FastAPI(lifespan=lifespan)
    with pytest.raises(AnalysisError, match='MODEL_ASSETS_INVALID'):
        with TestClient(app):
            pass
    assert app.state.text_analysis_state == 'FAILED'
    assert app.state.text_analysis_runtime is None


@pytest.mark.skipif(os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true',
                    reason='Set RUN_REAL_TEXT_ANALYSIS_TESTS=true after preparing model assets')
def test_app_keeps_one_model_until_shutdown(monkeypatch, auth_runtime):
    import asyncio
    from sqlalchemy import text
    from library.translation_runtime import TranslationRuntime, TranslationSettings
    from service.text_analysis_profiles import initialize_policy
    from datetime import datetime, timezone

    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE matching_runtime, matching_policies, text_analysis_profiles CASCADE'))

    async def prepare():
        runtime = TranslationRuntime(TranslationSettings.from_environment())
        try:
            await runtime.start()
            async with auth_runtime.factory() as db, db.begin():
                await initialize_policy(db, runtime.profile, now=datetime.now(timezone.utc))
        finally:
            await runtime.close()

    asyncio.run(prepare())
    monkeypatch.setattr('main.session_factory', lambda: auth_runtime.factory)
    monkeypatch.setenv('TEXT_ANALYSIS_ENABLED', 'true')
    app = FastAPI(lifespan=lifespan)
    with TestClient(app):
        runtime = app.state.text_analysis_runtime
        assert runtime.ready and runtime.load_count == 1
        assert app.state.text_analysis_state == 'READY'
    assert app.state.text_analysis_runtime is None
    assert app.state.text_analysis_state == 'STOPPED'
    assert not runtime.ready
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE matching_runtime, matching_policies, text_analysis_profiles CASCADE'))


@pytest.mark.parametrize('code', ['MATCHING_POLICY_NOT_CONFIGURED', 'ANALYSIS_PROFILE_MISMATCH'])
def test_policy_failure_closes_model_before_startup_completes(monkeypatch, code):
    class Runtime:
        closed = False
        profile = {}

        def __init__(self, settings):
            pass

        async def start(self):
            pass

        async def close(self):
            Runtime.closed = True
            return True

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

    async def reject(db, profile):
        raise AnalysisError(code)

    monkeypatch.setenv('TEXT_ANALYSIS_ENABLED', 'true')
    monkeypatch.setattr('main.TranslationRuntime', Runtime)
    monkeypatch.setattr('main.session_factory', lambda: Session)
    monkeypatch.setattr('main.active_policy', reject)
    app = FastAPI(lifespan=lifespan)
    with pytest.raises(AnalysisError, match=code), TestClient(app):
        pass
    assert Runtime.closed and app.state.text_analysis_state == 'FAILED'
    assert app.state.text_analysis_runtime is None
