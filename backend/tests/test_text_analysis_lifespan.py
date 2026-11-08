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
def test_app_keeps_one_model_until_shutdown(monkeypatch):
    monkeypatch.setenv('TEXT_ANALYSIS_ENABLED', 'true')
    app = FastAPI(lifespan=lifespan)
    with TestClient(app):
        runtime = app.state.text_analysis_runtime
        assert runtime.ready and runtime.load_count == 1
        assert app.state.text_analysis_state == 'READY'
    assert app.state.text_analysis_runtime is None
    assert app.state.text_analysis_state == 'STOPPED'
    assert not runtime.ready
