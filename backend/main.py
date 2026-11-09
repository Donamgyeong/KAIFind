from contextlib import asynccontextmanager
import os

from fastapi import FastAPI

from router import api_router
from library.photo_http import install_photo_log_filter
from library.translation_runtime import TranslationRuntime, TranslationSettings
from library.database import session_factory
from library.notification_settings import NotificationSettings
from service.email_worker import EmailWorker
from service.notification_worker import NotificationWorker
from service.keyword_worker import KeywordWorker
from service.outbox_worker import AnalysisWorker
from service.matching_worker import MatchingWorker
from service.text_analysis_profiles import active_policy


@asynccontextmanager
async def lifespan(app):
    email_settings = NotificationSettings.from_environment()
    enabled = os.getenv('TEXT_ANALYSIS_ENABLED', 'true').lower()
    if enabled not in {'true', 'false'}:
        raise ValueError('TEXT_ANALYSIS_ENABLED must be true or false')
    app.state.text_analysis_runtime = None
    app.state.text_analysis_state = 'DISABLED'
    runtime = None
    worker = None
    matching_worker = None
    email_worker = None
    notification_worker = None
    keyword_worker = None
    started = False
    try:
        if enabled == 'true':
            app.state.text_analysis_state = 'STARTING'
            try:
                runtime = TranslationRuntime(TranslationSettings.from_environment())
                await runtime.start()
                async with session_factory()() as db:
                    await active_policy(db, runtime.profile)
                worker = AnalysisWorker(runtime, session_factory())
                worker.start()
                matching_worker = MatchingWorker(session_factory())
                matching_worker.start()
                keyword_worker = KeywordWorker(runtime, session_factory())
                keyword_worker.start()
            except BaseException:
                app.state.text_analysis_state = 'FAILED'
                raise
            app.state.text_analysis_runtime = runtime
            app.state.text_analysis_state = 'READY'
            started = True
        notification_worker = NotificationWorker(session_factory())
        notification_worker.start()
        if email_settings.enabled:
            email_worker = EmailWorker(session_factory(), email_settings)
            email_worker.start()
        app.state.notification_email_settings = email_settings
        yield
    finally:
        if email_worker is not None:
            await email_worker.close()
        if notification_worker is not None:
            await notification_worker.close()
        if matching_worker is not None:
            await matching_worker.close()
        if keyword_worker is not None:
            await keyword_worker.close()
        if worker is not None:
            await worker.close()
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
