"""Bounded reconciliation and audited manual retry; caller owns transaction."""
from sqlalchemy import select

from library.matching_lock import lock_matching_categories
from model import FoundItem, OutboxEvent
from service.audit import append_audit
from service.text_analysis import KINDS, _request, eligible
from service.text_analysis_profiles import active_policy


async def repair_batch(db, *, kind, now, after=None, limit=100):
    """Keyset page. Return the cursor; callers commit each page separately."""
    if not 1 <= limit <= 1000:
        raise ValueError('Invalid repair batch size')
    model, features, column, _ = KINDS[kind]
    _, profile = await active_policy(db)
    query = select(model.id, model.category_id).order_by(model.id).limit(limit)
    if after is not None:
        query = query.where(model.id > after)
    rows = (await db.execute(query)).all()
    await lock_matching_categories(db, [row.category_id for row in rows])
    for row in rows:
        owner = (await db.execute(select(model).where(model.id == row.id)
            .with_for_update())).scalar_one_or_none()
        if owner is None:
            continue
        if owner.category_id != row.category_id:
            raise RuntimeError('CONCURRENT_MODIFICATION')
        if not eligible(owner, now):
            continue
        feature = (await db.execute(select(features).where(
            getattr(features, column) == owner.id, features.profile_id == profile.id,
            features.text_version == owner.text_version,
        ))).scalar_one_or_none()
        event_exists = feature is not None and (await db.execute(select(OutboxEvent.id).where(
            OutboxEvent.aggregate_id == feature.id, OutboxEvent.event_type == kind,
        ))).first() is not None
        if feature is None or (feature.status in {'PENDING', 'PROCESSING'} and not event_exists):
            await _request(db, owner, now, analyze=True)
    return rows[-1].id if rows else None


async def retry_failed(db, *, event_id, now):
    # Reuse the consumer's category/owner/feature/event lock order.
    snapshot = await db.get(OutboxEvent, event_id)
    if snapshot is None or snapshot.event_type not in KINDS or snapshot.failed_at is None:
        raise ValueError('FAILED_ANALYSIS_EVENT_REQUIRED')
    owner_model, feature_model, column, _ = KINDS[snapshot.event_type]
    feature = await db.get(feature_model, snapshot.aggregate_id)
    if feature is None:
        raise ValueError('ANALYSIS_TARGET_MISSING')
    owner_id = getattr(feature, column)
    category = (await db.execute(select(owner_model.category_id).where(owner_model.id == owner_id))).scalar_one()
    await lock_matching_categories(db, [category])
    owner = (await db.execute(select(owner_model).where(owner_model.id == owner_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if owner.category_id != category:
        raise RuntimeError('CONCURRENT_MODIFICATION')
    feature = (await db.execute(select(feature_model).where(feature_model.id == feature.id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    event = (await db.execute(select(OutboxEvent).where(OutboxEvent.id == event_id)
        .with_for_update().execution_options(populate_existing=True))).scalar_one()
    if event.failed_at is None or not eligible(owner, now):
        raise ValueError('FAILED_ANALYSIS_EVENT_REQUIRED')
    _, profile = await active_policy(db)
    if feature.text_version != owner.text_version or feature.profile_id != profile.id:
        feature.status = 'SUPERSEDED'
        feature.completed_at = now
        feature.last_error_code = None
        event.failed_at = None
        event.cancelled_at = now
        event.last_error_code = None
        await _request(db, owner, now, analyze=True)
    else:
        feature.status = 'PENDING'
        feature.completed_at = None
        feature.last_error_code = None
        event.failed_at = None
        event.attempts = 0
        event.next_attempt_at = now
        event.last_error_code = None
    feature.updated_at = now
    append_audit(
        db, None, 'TEXT_ANALYSIS_RETRIED',
        'FOUND_ITEM' if isinstance(owner, FoundItem) else 'LOST_REPORT',
        owner.id, now, eventId=event.id,
    )
