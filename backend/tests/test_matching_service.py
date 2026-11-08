"""Candidate lifecycle and generation fencing on real PostgreSQL."""
import asyncio
from datetime import date, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text, update

from library.matching_lock import lock_matching_categories
from library.text_analysis_types import AnalysisError
from model import (
    AuditLog, Building, Category, FoundItem, FoundItemTextFeature, LostReport,
    LostReportBuilding, LostReportTextFeature, MatchCandidate, MatchEvaluationJob,
)
from service.matching import read_matches, matching_progress
from service.matching_worker import MatchingWorker
from service.matching_maintenance import repair_batch, retry_failed
from service.text_analysis import request_found_item_analysis, request_item_reevaluation
from test_analysis_worker import analysis_env, prepare, worker as analysis_worker


async def setup(env, *, building=True, ready=True):
    # Normalize fixture dates relative to its deterministic request clock.
    async with env.factory() as db, db.begin():
        await db.execute(update(LostReport).where(LostReport.id == env.ids['report']).values(
            lost_date_from=date(2026, 11, 1), lost_date_to=date(2026, 11, 1),
        ))
        await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(found_at=env.clock()))
        if building:
            db.add(LostReportBuilding(report_id=env.ids['report'], building_id=env.ids['building']))
    await prepare(env)
    await prepare(env, report=True)
    if ready:
        while await analysis_worker(env).run_once():
            pass


def worker(env, **kwargs):
    return MatchingWorker(env.factory, clock=env.clock, **kwargs)


async def drain(env):
    w = worker(env)
    for _ in range(12):
        if not await w.run_once():
            return
    raise AssertionError('Matching jobs did not drain')


async def page(env, **kwargs):
    async with env.factory() as db:
        return await read_matches(db, report_id=env.ids['report'], now=env.clock(), internal=True, **kwargs)


@pytest.mark.asyncio
@pytest.mark.parametrize('building', [False, True])
async def test_matching_ready_reasons_and_idempotent_history(analysis_env, building):
    env = analysis_env
    await setup(env, building=building)
    assert (await page(env)).matching_status == 'PENDING'
    await drain(env)
    result = await page(env)
    assert result.is_complete and result.total_elements == 1
    first = result.items[0]
    assert first.matched_by == (['BUILDING', 'KEYWORD'] if building else ['KEYWORD'])
    assert result.model_dump(mode='json', by_alias=True)['items'][0]['matchedAt'].endswith('+09:00')
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        await request_item_reevaluation(db, item=item, now=env.clock())
    await drain(env)
    second = (await page(env)).items[0]
    assert (first.candidate_id, first.matched_at) == (second.candidate_id, second.matched_at)
    async with env.factory() as db:
        assert len((await db.scalars(select(MatchCandidate))).all()) == 1
        progress = await matching_progress(db, report=await db.get(LostReport, env.ids['report']), now=env.clock())
        assert progress.matching_status == 'READY'
    assert (await page(env, page=9)).items == []
    assert (await page(env, page=9)).total_elements == 1


@pytest.mark.asyncio
async def test_pending_building_candidate_and_failed_analysis(analysis_env):
    env = analysis_env
    await setup(env, ready=False)
    await drain(env)
    result = await page(env)
    assert not result.is_complete and result.items[0].matched_by == ['BUILDING']
    assert result.analysis_status == result.matching_status == 'PENDING'
    env.runtime.error = AnalysisError('ANALYSIS_FAILED')
    while await analysis_worker(env).run_once():
        pass
    assert (await page(env)).matching_status == 'FAILED'
    assert (await page(env)).total_elements == 1


@pytest.mark.asyncio
async def test_stale_candidate_excluded_then_reactivated_without_resetting_first_match(analysis_env):
    env = analysis_env
    await setup(env)
    await drain(env)
    original = (await page(env)).items[0]
    async with env.factory() as db, db.begin():
        await lock_matching_categories(db, [env.ids['category']])
        item = await db.get(FoundItem, env.ids['item'])
        item.found_at = env.clock() - timedelta(days=20)
        await db.flush()
        await request_item_reevaluation(db, item=item, now=env.clock())
    assert (await page(env)).total_elements == 0
    await drain(env)
    async with env.factory() as db:
        assert not (await db.get(MatchCandidate, original.candidate_id)).active
    env.clock.advance(seconds=1)
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        item.found_at = env.clock()
        await db.flush()
        await request_item_reevaluation(db, item=item, now=env.clock())
    await drain(env)
    result = (await page(env)).items[0]
    assert result.candidate_id == original.candidate_id and result.matched_at == original.matched_at


@pytest.mark.asyncio
async def test_category_move_cleans_old_link_and_new_text_hides_old_keyword(analysis_env):
    env = analysis_env
    await setup(env, building=False)
    await drain(env)
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        item.description = 'Changed'
        await db.flush()
        await db.refresh(item)
        await request_found_item_analysis(db, item=item, now=env.clock())
    assert (await page(env)).total_elements == 0
    await analysis_worker(env).run_once()
    await drain(env)
    assert (await page(env)).total_elements == 1
    async with env.factory() as db, db.begin():
        category = Category(name_ko='Other', name_en='Other')
        db.add(category)
        await db.flush()
        item = await db.get(FoundItem, env.ids['item'])
        await lock_matching_categories(db, [item.category_id, category.id])
        item.category_id = category.id
        await db.flush()
        await request_item_reevaluation(db, item=item, now=env.clock())
    await drain(env)
    assert (await page(env)).total_elements == 0
    async with env.factory() as db:
        assert not (await db.scalar(select(MatchCandidate))).active


@pytest.mark.asyncio
@pytest.mark.parametrize('close', ['CLOSED', 'RESOLVED', 'expired', 'deleted'])
async def test_terminal_changes_preserve_only_permitted_history(analysis_env, close):
    env = analysis_env
    await setup(env)
    await drain(env)
    async with env.factory() as db, db.begin():
        if close == 'deleted':
            item = await db.get(FoundItem, env.ids['item'])
            item.deleted_at = env.clock()
        else:
            report = await db.get(LostReport, env.ids['report'])
            if close == 'expired':
                report.expires_at = env.clock()
            else:
                report.status = close
                report.closed_at = env.clock()
    result = await page(env)
    assert result.is_complete
    assert result.total_elements == (0 if close == 'deleted' else 1)
    async with env.factory() as db:
        assert (await db.scalar(select(LostReport).where(LostReport.id == env.ids['report']))).status == (
            close if close in {'CLOSED', 'RESOLVED'} else 'OPEN')


@pytest.mark.asyncio
async def test_new_opposite_owner_invalidates_completed_status(analysis_env):
    env = analysis_env
    await setup(env)
    await drain(env)
    assert (await page(env)).is_complete
    async with env.factory() as db, db.begin():
        item = FoundItem(
            finder_id=env.ids['finder'], category_id=env.ids['category'],
            found_building_id=env.ids['building'], title='New', description='New',
            found_location_description='Desk', found_at=env.clock(), expires_at=env.clock() + timedelta(days=30),
        )
        db.add(item)
        await db.flush()
        await request_found_item_analysis(db, item=item, now=env.clock())
    assert (await page(env)).matching_status == 'PENDING'
    assert (await page(env)).total_elements == 1
    await analysis_worker(env).run_once()
    await drain(env)
    assert (await page(env)).is_complete
    assert (await page(env)).total_elements == 2


@pytest.mark.asyncio
async def test_claim_expiry_and_late_success_failure_are_fenced(analysis_env):
    env = analysis_env
    await setup(env)
    w = worker(env)
    first = await w.claim()
    # There is another owner job; isolate this claim for the fencing checks.
    async with env.factory() as db, db.begin():
        await db.execute(update(MatchEvaluationJob).where(MatchEvaluationJob.id != first.id).values(
            next_attempt_at=env.clock() + timedelta(days=1)))
    assert await w.claim() is None
    env.clock.advance(seconds=61)
    second = await w.claim()
    assert second.id == first.id and first.lease_token != second.lease_token
    await w.process(first)
    await w.failure(first, AnalysisError('STALE_FAILURE'))
    assert (await page(env)).total_elements == 0
    await w.process(second)
    assert (await page(env)).total_elements == 1
    async with env.factory() as db:
        job = await db.get(MatchEvaluationJob, first.id)
        assert job.completed_generation == job.requested_generation and job.failed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize('outcome', ['success', 'failure'])
async def test_new_generation_survives_old_completion_and_failure(analysis_env, outcome):
    env = analysis_env
    await setup(env)
    w = worker(env)
    old = await w.claim()
    async with env.factory() as db, db.begin():
        await db.execute(update(MatchEvaluationJob).where(MatchEvaluationJob.id == old.id).values(
            requested_generation=MatchEvaluationJob.requested_generation + 1))
    if outcome == 'success':
        await w.process(old)
    else:
        await w.failure(old, AnalysisError('OLD_GENERATION_FAILED'))
    async with env.factory() as db:
        job = await db.get(MatchEvaluationJob, old.id)
        assert job.completed_generation == (old.claimed_generation if outcome == 'success' else 0)
        assert job.completed_generation < job.requested_generation and job.failed_at is None
    await drain(env)
    assert (await page(env)).is_complete


@pytest.mark.asyncio
async def test_two_workers_do_not_duplicate_candidates(analysis_env):
    env = analysis_env
    await setup(env)
    await asyncio.gather(worker(env).run_once(), worker(env).run_once())
    await drain(env)
    async with env.factory() as db:
        assert len((await db.scalars(select(MatchCandidate))).all()) == 1
    assert (await page(env)).is_complete


@pytest.mark.asyncio
async def test_repair_missing_job_and_audited_retry(analysis_env):
    env = analysis_env
    await setup(env)
    async with env.factory() as db, db.begin():
        await db.execute(delete(MatchEvaluationJob).where(MatchEvaluationJob.item_id == env.ids['item']))
        await repair_batch(db, model=FoundItem, now=env.clock())
    w = worker(env, max_attempts=1)
    job = await w.claim()
    await w.failure(job, AnalysisError('MATCH_EVALUATION_FAILED'))
    assert (await page(env)).matching_status == 'FAILED'
    async with env.factory() as db, db.begin():
        await retry_failed(db, job_id=job.id, now=env.clock())
    await drain(env)
    assert (await page(env)).is_complete
    async with env.factory() as db:
        audit = await db.scalar(select(AuditLog).where(
            AuditLog.action == 'MATCH_EVALUATION_RETRIED',
            AuditLog.event_metadata['eventId'].astext == str(job.id),
        ))
        assert audit.actor_type == 'SYSTEM' and audit.event_metadata == {'eventId': str(job.id)}


@pytest.mark.asyncio
async def test_expiry_at_final_write_rolls_back_candidate_changes(analysis_env, monkeypatch):
    env = analysis_env
    await setup(env)
    w = worker(env)
    job = await w.claim()
    save = w.save_candidate

    async def expire(*args):
        await save(*args)
        env.clock.advance(seconds=61)

    monkeypatch.setattr(w, 'save_candidate', expire)
    await w.process(job)
    assert (await page(env)).total_elements == 0
    async with env.factory() as db:
        current = await db.get(MatchEvaluationJob, job.id)
        assert current.completed_generation == 0
    await drain(env)
    assert (await page(env)).is_complete


@pytest.mark.asyncio
async def test_category_move_before_lock_retries_whole_workset(analysis_env, monkeypatch):
    import service.matching_worker as module
    env = analysis_env
    await setup(env)
    w = worker(env)
    job = await w.claim()
    lock = module.lock_matching_categories

    async def move(db, categories):
        async with env.factory() as other, other.begin():
            category = Category(name_ko='Moved', name_en='Moved')
            other.add(category)
            await other.flush()
            await other.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                category_id=category.id, version=FoundItem.version + 1))
        await lock(db, categories)

    monkeypatch.setattr(module, 'lock_matching_categories', move)
    await w.process(job)
    async with env.factory() as db:
        current = await db.get(MatchEvaluationJob, job.id)
        assert current.completed_generation == 0 and current.lease_token is None
    assert (await page(env)).total_elements == 0


@pytest.mark.asyncio
async def test_heartbeat_renews_matching_lease(analysis_env):
    from contextlib import suppress
    env = analysis_env
    await setup(env)
    w = worker(env, lease_seconds=0.3)
    job = await w.claim()
    pulse = asyncio.create_task(w.heartbeat(job))
    try:
        env.clock.advance(milliseconds=200)
        await asyncio.sleep(0.18)
        async with env.factory() as db:
            current = await db.get(MatchEvaluationJob, job.id)
            assert current.lease_until > job.lease_until
    finally:
        pulse.cancel()
        with suppress(asyncio.CancelledError):
            await pulse


@pytest.mark.asyncio
async def test_processing_precedence_missing_jobs_and_terminal_failure(analysis_env):
    env = analysis_env
    await setup(env)
    w = worker(env)
    job = await w.claim()
    assert (await page(env)).matching_status == 'PROCESSING'
    await w.failure(job, AnalysisError('MATCH_EVALUATION_FAILED'))
    assert (await page(env)).matching_status == 'FAILED'
    async with env.factory() as db, db.begin():
        await retry_failed(db, job_id=job.id, now=env.clock())
    env.clock.advance(seconds=400)
    await drain(env)
    assert (await page(env)).is_complete
    async with env.factory() as db, db.begin():
        await db.execute(delete(MatchEvaluationJob).where(MatchEvaluationJob.id == job.id))
    assert (await page(env)).matching_status == 'PENDING'


@pytest.mark.asyncio
async def test_kst_boundary_and_mismatched_canonical_keywords(analysis_env):
    env = analysis_env
    await setup(env, building=False)
    # Immutable READY features cannot be changed; generate a new version instead.
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        item.description = 'Unrelated'
        item.found_at = env.clock().replace(day=1, hour=15) - timedelta(microseconds=1)
        await db.flush()
        await db.refresh(item)
        feature = await request_found_item_analysis(db, item=item, now=env.clock())
        feature.status = 'READY'
        feature.translated_text = 'Unrelated'
        feature.keywords = ['lemma:umbrella']
        feature.attributes = {}
        feature.completed_at = env.clock()
    await drain(env)
    assert (await page(env)).is_complete and (await page(env)).total_elements == 0
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        # 15:00 UTC is midnight KST: the preceding instant is still November 1.
        report = await db.get(LostReport, env.ids['report'])
        report.lost_date_from = report.lost_date_to = date(2026, 11, 2)
        db.add(LostReportBuilding(report_id=report.id, building_id=env.ids['building']))
        await db.flush()
        from service.text_analysis import request_report_reevaluation
        await request_report_reevaluation(db, report=report, now=env.clock())
        await request_item_reevaluation(db, item=item, now=env.clock())
    await drain(env)
    assert (await page(env)).total_elements == 0
    async with env.factory() as db, db.begin():
        item = await db.get(FoundItem, env.ids['item'])
        item.found_at += timedelta(microseconds=1)
        await db.flush()
        await request_item_reevaluation(db, item=item, now=env.clock())
    await drain(env)
    assert (await page(env)).items[0].matched_by == ['BUILDING']
