from contextlib import asynccontextmanager
import os

from fastapi import FastAPI

from router import api_router
from library.photo_http import install_photo_log_filter
from library.translation_runtime import TranslationRuntime, TranslationSettings


@asynccontextmanager
async def lifespan(app):
    enabled = os.getenv('TEXT_ANALYSIS_ENABLED', 'true').lower()
    if enabled not in {'true', 'false'}:
        raise ValueError('TEXT_ANALYSIS_ENABLED must be true or false')
    app.state.text_analysis_runtime = None
    app.state.text_analysis_state = 'DISABLED'
    runtime = None
    started = False
    try:
        if enabled == 'true':
            app.state.text_analysis_state = 'STARTING'
            try:
                runtime = TranslationRuntime(TranslationSettings.from_environment())
                await runtime.start()
            except BaseException:
                app.state.text_analysis_state = 'FAILED'
                raise
            app.state.text_analysis_runtime = runtime
            app.state.text_analysis_state = 'READY'
            started = True
        yield
    finally:
        if runtime is not None:
            if started:
                app.state.text_analysis_state = 'STOPPING'
            drained = await runtime.close()
            app.state.text_analysis_runtime = None
            if started and drained:
                app.state.text_analysis_state = 'STOPPED'


install_photo_log_filter()
app = FastAPI(title="KAIFind API", version="0.1.0", lifespan=lifespan)
app.include_router(api_router)


@app.get("/")
async def read_root():
    return {"Hello": "World"}
