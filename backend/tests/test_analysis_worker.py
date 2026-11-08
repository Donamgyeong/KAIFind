"""Real PostgreSQL service transactions, leases, recovery and runtime integration."""
import asyncio
from datetime import timedelta
import os
from types import SimpleNamespace

import pytest
from sqlalchemy import delete, select, text, update

from library.text_analysis_types import AnalysisError, AnalysisResult, canonical_json
from model import (
    AuditLog, FoundItem, FoundItemTextFeature, LostReport, LostReportPrivateDetail,
    LostReportTextFeature, MatchEvaluationJob, OutboxEvent,
)
from service.outbox_worker import AnalysisWorker
from service.text_analysis import (
    KINDS, analysis_status, request_found_item_analysis, request_lost_report_analysis,
    request_item_reevaluation,
)
from service.text_analysis_maintenance import repair_batch, retry_failed
from service.text_analysis_profiles import active_policy, fingerprint, initialize_policy
from test_schema import seed as seed_fixture, report as seed_report


PROFILE = dict(
    model_name='Helsinki-NLP/opus-mt_tiny_kor-eng', model_revision='a' * 40,
    tokenizer_revision='a' * 40, input_format_version='title-description-json-v1',
    language_rule_version='hangul-or-assumed-english-v1', keyword_rule_version='spacy-wordnet-keywords-v2',
    runtime_config={'test': True},
)
PROFILE['fingerprint'] = fingerprint(PROFILE)


class Runtime:
    profile = PROFILE
    calls = 0
    hook = None
    error = None

    async def analyze(self, value):
        self.calls += 1
        if self.hook:
            await self.hook()
        if self.error:
            raise self.error
        return AnalysisResult('EN', value.source_hash, value.canonical(), ('lemma:wallet',), {},
                              self.profile['fingerprint'])


@pytest.fixture
def analysis_env(auth_runtime):
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE categories, buildings, matching_runtime, matching_policies, text_analysis_profiles CASCADE'))
        db.execute(delete(OutboxEvent).where(OutboxEvent.event_type.in_(KINDS)))
        ids = seed_fixture.__wrapped__(db)
        rid = seed_report(db, ids)
        db.execute(LostReportPrivateDetail.__table__.insert().values(report_id=rid, details='SECRET'))
        ids['report'] = rid
    yield SimpleNamespace(factory=auth_runtime.factory, clock=auth_runtime.clock,
                          ids=ids, runtime=Runtime(), sync=auth_runtime.sync_engine)
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE categories, buildings, matching_runtime, matching_policies, text_analysis_profiles CASCADE'))
        db.execute(delete(OutboxEvent).where(OutboxEvent.event_type.in_(KINDS)))


async def prepare(env, *, report=False):
    async with env.factory() as db, db.begin():
        await initialize_policy(db, env.runtime.profile, now=env.clock())
        owner = await db.get(LostReport if report else FoundItem, env.ids['report' if report else 'item'])
        feature = await (request_lost_report_analysis(db, report=owner, now=env.clock()) if report
                         else request_found_item_analysis(db, item=owner, now=env.clock()))
        return feature.id


def worker(env, **kwargs):
    return AnalysisWorker(env.runtime, env.factory, clock=env.clock, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('is_report', [False, True])
async def test_request_worker_ready_and_generation(analysis_env, is_report):
    env = analysis_env
    fid = await prepare(env, report=is_report)
    assert await worker(env).run_once()
    async with env.factory() as db:
        feature = await db.get(LostReportTextFeature if is_report else FoundItemTextFeature, fid)
        assert feature.status == 'READY' and feature.keywords == ['lemma:wallet']
        assert 'SECRET' not in feature.translated_text
        event = (await db.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == fid))).scalar_one()
        assert event.processed_at and not event.lease_token
        assert set(event.payload) == {'featureId', 'reportId' if is_report else 'itemId', 'profileId', 'textVersion'}
        job = (await db.execute(select(MatchEvaluationJob))).scalar_one()
        assert job.requested_generation == 2 and job.completed_generation == 0
        owner = await db.get(LostReport if is_report else FoundItem, env.ids['report' if is_report else 'item'])
        assert await analysis_status(db, owner=owner) == 'READY'
    assert not await worker(env).run_once()


@pytest.mark.asyncio
async def test_idempotence_rollback_and_non_text_reuse(analysis_env):
    env = analysis_env
    fid = await prepare(env)
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        assert (await request_found_item_analysis(db, item=item, now=env.clock())).id == fid
        await request_item_reevaluation(db, item=item, now=env.clock())
    assert await worker(env).run_once()
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        assert (await request_found_item_analysis(db, item=item, now=env.clock())).id == fid
        assert len((await db.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == fid))).all()) == 1
        item.description = 'New input'
        await db.flush()
        await db.refresh(item)
        new = await request_found_item_analysis(db, item=item, now=env.clock())
        new_id = new.id
        await db.rollback()
    async with env.factory() as db:
        assert await db.get(FoundItemTextFeature, new_id) is None
    assert env.runtime.calls == 1


@pytest.mark.asyncio
async def test_claim_fencing_and_expired_late_failure(analysis_env):
    env = analysis_env
    fid = await prepare(env)
    first, second = worker(env), worker(env)
    old = await first.claim()
    assert await second.claim() is None
    env.clock.advance(seconds=61)
    current = await second.claim()
    assert old.lease_token != current.lease_token
    await first.process(old)
    await first.failure(old, AnalysisError('ANALYSIS_FAILED'))
    assert env.runtime.calls == 0
    await second.process(current)
    async with env.factory() as db:
        assert (await db.get(FoundItemTextFeature, fid)).status == 'READY'


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['text', 'delete', 'close', 'category', 'version'])
async def test_change_during_inference(analysis_env, change):
    env = analysis_env
    is_report = change == 'close'
    fid = await prepare(env, report=is_report)

    async def mutate():
        async with env.factory() as db, db.begin():
            if is_report:
                await db.execute(update(LostReport).where(LostReport.id == env.ids['report']).values(
                    status='CLOSED', closed_at=env.clock(), version=LostReport.version + 1,
                ))
            elif change == 'delete':
                await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                    deleted_at=env.clock(), version=FoundItem.version + 1,
                ))
            elif change == 'category':
                from uuid import uuid4
                from model import Category
                category_id = uuid4()
                db.add(Category(id=category_id, name_ko=str(category_id), name_en=str(category_id)))
                await db.flush()
                await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                    category_id=category_id, version=FoundItem.version + 1,
                ))
            elif change == 'version':
                await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                    found_location_description='Other desk', version=FoundItem.version + 1,
                ))
            else:
                await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                    description='Changed input', version=FoundItem.version + 1,
                ))
    env.runtime.hook = mutate
    await worker(env).run_once()
    async with env.factory() as db:
        feature = await db.get(LostReportTextFeature if is_report else FoundItemTextFeature, fid)
        event = (await db.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == fid))).scalar_one()
        if change == 'delete':
            assert feature is None and event.cancelled_at
        elif change in {'category', 'version'}:
            assert feature.status == 'READY' and event.processed_at
        else:
            assert feature.status == 'SUPERSEDED' and event.cancelled_at


@pytest.mark.asyncio
@pytest.mark.parametrize('retryable', [True, False])
async def test_failure_retry_and_audited_manual_retry(analysis_env, retryable):
    env = analysis_env
    fid = await prepare(env)
    env.runtime.error = AnalysisError('ANALYSIS_TIMEOUT' if retryable else 'TEXT_CHUNK_LIMIT', retryable=retryable)
    w = worker(env, max_attempts=2)
    await w.run_once()
    async with env.factory() as db:
        feature = await db.get(FoundItemTextFeature, fid)
        assert feature.status == ('PENDING' if retryable else 'FAILED')
    env.clock.advance(seconds=400)
    if retryable:
        await w.run_once()
    async with env.factory() as db, db.begin():
        event = (await db.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == fid))).scalar_one()
        assert event.failed_at and not event.processed_at and not event.lease_token
        await retry_failed(db, event_id=event.id, now=env.clock())
    env.runtime.error = None
    await w.run_once()
    async with env.factory() as db:
        assert (await db.get(FoundItemTextFeature, fid)).status == 'READY'
        assert (await db.execute(select(AuditLog).where(AuditLog.action == 'TEXT_ANALYSIS_RETRIED'))).first()


@pytest.mark.asyncio
async def test_policy_validation_and_repair(analysis_env):
    env = analysis_env
    async with env.factory() as db:
        with pytest.raises(AnalysisError, match='MATCHING_POLICY_NOT_CONFIGURED'):
            await active_policy(db)
    async with env.factory() as db, db.begin():
        await initialize_policy(db, env.runtime.profile, now=env.clock())
        with pytest.raises(AnalysisError, match='PROFILE_FINGERPRINT_INVALID'):
            await active_policy(db, {**PROFILE, 'fingerprint': 'b' * 64})
        cursor = await repair_batch(db, kind=next(iter(KINDS)), now=env.clock(), limit=1)
        assert cursor == env.ids['item']
    async with env.factory() as db, db.begin():
        assert await repair_batch(db, kind=next(iter(KINDS)), now=env.clock(), after=cursor) is None
        await repair_batch(db, kind=next(iter(KINDS)), now=env.clock())
        assert len((await db.execute(select(OutboxEvent).where(OutboxEvent.event_type.in_(KINDS)))).all()) == 1
    assert await worker(env).run_once()


@pytest.mark.asyncio
async def test_heartbeat_keeps_long_inference_owned(analysis_env):
    env = analysis_env
    await prepare(env)
    # Use real elapsed time for this lease, unlike deterministic retry tests.
    w = AnalysisWorker(env.runtime, env.factory, lease_seconds=0.3)
    async def slow():
        await asyncio.sleep(0.65)
        assert await AnalysisWorker(env.runtime, env.factory, lease_seconds=0.3).claim() is None
    env.runtime.hook = slow
    # Fixture timestamps precede actual clock; eligible item is not date-gated.
    assert await w.run_once()
    async with env.factory() as db:
        assert (await db.execute(select(FoundItemTextFeature.status))).scalar_one() == 'READY'


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true', reason='Real model opt-in')
async def test_real_model_outbox_to_ready(analysis_env):
    from library.translation_runtime import TranslationRuntime, TranslationSettings
    env = analysis_env
    runtime = TranslationRuntime(TranslationSettings.from_environment())
    try:
        await runtime.start()
        env.runtime = runtime
        async with env.factory() as db, db.begin():
            item = await db.get(FoundItem, env.ids['item'])
            item.description = '검은 지갑입니다.'
        fid = await prepare(env)
        assert await worker(env).run_once()
        async with env.factory() as db:
            feature = await db.get(FoundItemTextFeature, fid)
            assert feature.status == 'READY' and 'lemma:wallet' in feature.keywords
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_simultaneous_claims_and_late_success_are_fenced(analysis_env):
    env = analysis_env
    fid = await prepare(env)
    w1, w2 = worker(env), worker(env)
    claims = await asyncio.gather(w1.claim(), w2.claim())
    assert sum(event is not None for event in claims) == 1
    old = next(event for event in claims if event is not None)

    async def expire_and_reclaim():
        env.clock.advance(seconds=61)
        replacement = await w2.claim()
        assert replacement and replacement.lease_token != old.lease_token
    env.runtime.hook = expire_and_reclaim
    await w1.process(old)
    async with env.factory() as db:
        feature = await db.get(FoundItemTextFeature, fid)
        assert feature.status == 'PROCESSING' and feature.translated_text is None
        event = await db.get(OutboxEvent, old.id)
        assert event.processed_at is None and event.attempts == 2


@pytest.mark.asyncio
async def test_busy_runtime_leaves_work_in_db(analysis_env):
    env = analysis_env
    await prepare(env)
    future = asyncio.get_running_loop().create_future()
    env.runtime._future = future
    try:
        assert not await worker(env).run_once()
        async with env.factory() as db:
            event = (await db.execute(select(OutboxEvent).where(OutboxEvent.event_type.in_(KINDS)))).scalar_one()
            assert event.attempts == 0 and event.lease_token is None
    finally:
        future.set_result(None)


@pytest.mark.asyncio
async def test_new_request_preserves_generation_lease_and_revives_failed_job(analysis_env):
    from uuid import uuid4
    env = analysis_env
    await prepare(env)
    token = uuid4()
    async with env.factory() as db, db.begin():
        job = (await db.execute(select(MatchEvaluationJob))).scalar_one()
        job.claimed_generation = 1
        job.lease_token = token
        job.lease_until = env.clock() + timedelta(seconds=60)
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        await request_item_reevaluation(db, item=item, now=env.clock())
    async with env.factory() as db, db.begin():
        job = (await db.execute(select(MatchEvaluationJob))).scalar_one()
        assert job.requested_generation == 2 and job.claimed_generation == 1
        assert job.lease_token == token and job.completed_generation == 0
        job.claimed_generation = job.lease_token = job.lease_until = None
        job.failed_at = env.clock()
        job.last_error_code = 'EVALUATION_FAILED'
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        await request_item_reevaluation(db, item=item, now=env.clock())
    async with env.factory() as db:
        job = (await db.execute(select(MatchEvaluationJob))).scalar_one()
        assert job.requested_generation == 3 and job.failed_at is None


@pytest.mark.asyncio
async def test_manual_retry_supersedes_stale_input_and_repair_keeps_failures(analysis_env):
    env = analysis_env
    fid = await prepare(env)
    env.runtime.error = AnalysisError('TEXT_CHUNK_LIMIT')
    await worker(env).run_once()
    async with env.factory() as db, db.begin():
        await repair_batch(db, kind=next(iter(KINDS)), now=env.clock())
        assert (await db.get(FoundItemTextFeature, fid)).status == 'FAILED'
        item = await db.get(FoundItem, env.ids['item'])
        item.description = 'Latest description'
    async with env.factory() as db, db.begin():
        event = (await db.execute(select(OutboxEvent).where(OutboxEvent.aggregate_id == fid))).scalar_one()
        await retry_failed(db, event_id=event.id, now=env.clock())
    async with env.factory() as db:
        assert (await db.get(FoundItemTextFeature, fid)).status == 'SUPERSEDED'
        assert len((await db.execute(select(FoundItemTextFeature))).all()) == 2


@pytest.mark.asyncio
async def test_closed_report_retains_analysis_and_refuses_new_work(analysis_env):
    env = analysis_env
    await prepare(env, report=True)
    await worker(env).run_once()
    async with env.factory() as db, db.begin():
        report = await db.get(LostReport, env.ids['report'])
        report.status = 'CLOSED'
        report.closed_at = env.clock()
        await db.flush()
        assert await request_lost_report_analysis(db, report=report, now=env.clock()) is None
        assert await analysis_status(db, owner=report) == 'READY'


@pytest.mark.asyncio
async def test_category_change_between_snapshot_and_lock_retries(analysis_env, monkeypatch):
    from uuid import uuid4
    from model import Category
    from library.matching_lock import lock_matching_categories
    env = analysis_env
    fid = await prepare(env)
    moved = False

    async def move_before_lock(db, category_ids):
        nonlocal moved
        if not moved:
            moved = True
            async with env.factory() as other, other.begin():
                category_id = uuid4()
                other.add(Category(id=category_id, name_ko=str(category_id), name_en=str(category_id)))
                await other.flush()
                await other.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                    category_id=category_id, version=FoundItem.version + 1,
                ))
        await lock_matching_categories(db, category_ids)
    monkeypatch.setattr('service.outbox_worker.lock_matching_categories', move_before_lock)
    w = worker(env)
    assert await w.run_once()
    assert env.runtime.calls == 0
    async with env.factory() as db:
        assert (await db.get(FoundItemTextFeature, fid)).status == 'PENDING'
    env.clock.advance(seconds=10)
    assert await w.run_once()
    async with env.factory() as db:
        assert (await db.get(FoundItemTextFeature, fid)).status == 'READY'
