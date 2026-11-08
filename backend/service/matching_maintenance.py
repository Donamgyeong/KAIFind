"""Bounded missing-job repair and audited matching retries; caller commits."""
from sqlalchemy import exists, select

from library.matching_lock import lock_matching_categories
from library.text_analysis_types import AnalysisError
from model import FoundItem, LostReport, MatchEvaluationJob
from service.audit import append_audit
from service.text_analysis import eligible, enqueue_reevaluation
from service.text_analysis_profiles import active_policy


async def repair_batch(db, *, model, now, after=None, limit=100):
    if model not in (FoundItem, LostReport) or not 1 <= limit <= 1000:
        raise ValueError('Invalid matching repair scope')
    policy, _ = await active_policy(db)
    column = MatchEvaluationJob.item_id if model is FoundItem else MatchEvaluationJob.report_id
    query = select(model.id, model.category_id).where(~exists(select(MatchEvaluationJob.id).where(
        column == model.id, MatchEvaluationJob.policy_id == policy.id,
    ))).order_by(model.id).limit(limit)
    if after is not None:
        query = query.where(model.id > after)
    rows = (await db.execute(query)).all()
    await lock_matching_categories(db, [r.category_id for r in rows])
    for row in rows:
        owner = (await db.scalars(select(model).where(model.id == row.id).with_for_update())).one_or_none()
        if owner is None:
            continue
        if owner.category_id != row.category_id:
            raise AnalysisError('CONCURRENT_MODIFICATION', retryable=True)
        if eligible(owner, now):
            await enqueue_reevaluation(db, owner=owner, policy_id=policy.id, now=now)
    return rows[-1].id if rows else None


async def retry_failed(db, *, job_id, now):
    snapshot = await db.get(MatchEvaluationJob, job_id)
    if snapshot is None or snapshot.failed_at is None:
        raise ValueError('FAILED_MATCHING_JOB_REQUIRED')
    model = FoundItem if snapshot.item_id is not None else LostReport
    owner_id = snapshot.item_id or snapshot.report_id
    category = await db.scalar(select(model.category_id).where(model.id == owner_id))
    if category is None:
        raise ValueError('MATCHING_TARGET_MISSING')
    await lock_matching_categories(db, [category])
    owner = (await db.scalars(select(model).where(model.id == owner_id)
        .with_for_update())).one_or_none()
    if owner is None or not eligible(owner, now):
        raise ValueError('MATCHING_TARGET_INELIGIBLE')
    if owner.category_id != category:
        raise AnalysisError('CONCURRENT_MODIFICATION', retryable=True)
    job = (await db.scalars(select(MatchEvaluationJob).where(MatchEvaluationJob.id == job_id)
        .with_for_update().execution_options(populate_existing=True))).one()
    policy, _ = await active_policy(db)
    if job.failed_at is None or job.policy_id != policy.id:
        raise ValueError('CURRENT_FAILED_MATCHING_JOB_REQUIRED')
    await enqueue_reevaluation(db, owner=owner, policy_id=policy.id, now=now)
    append_audit(db, None, 'MATCH_EVALUATION_RETRIED',
                 'FOUND_ITEM' if model is FoundItem else 'LOST_REPORT', owner.id, now, eventId=job.id)
