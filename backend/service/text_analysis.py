"""Durable analysis requests. Callers own transactions and category locks."""
from sqlalchemy import case, inspect, select
from sqlalchemy.dialects.postgresql import insert

from library.text_analysis_types import AnalysisInput
from library.text_input import source_language
from model import (
    FoundItem, FoundItemTextFeature, LostReport, LostReportTextFeature,
    MatchEvaluationJob, OutboxEvent,
)
from service.text_analysis_profiles import active_policy


KINDS = {
    'FOUND_ITEM_TEXT_ANALYSIS_REQUESTED': (FoundItem, FoundItemTextFeature, 'item_id', 'itemId'),
    'LOST_REPORT_TEXT_ANALYSIS_REQUESTED': (LostReport, LostReportTextFeature, 'report_id', 'reportId'),
}


def analysis_input(owner):
    return AnalysisInput(description=owner.description, title=getattr(owner, 'title', None))


def eligible(owner, now):
    if isinstance(owner, FoundItem):
        return owner.deleted_at is None
    return owner.status == 'OPEN' and owner.expires_at > now


async def enqueue_reevaluation(db, *, owner, policy_id, now):
    column = 'item_id' if isinstance(owner, FoundItem) else 'report_id'
    if not eligible(owner, now):
        return None
    statement = insert(MatchEvaluationJob).values(
        **{column: owner.id}, policy_id=policy_id, requested_generation=1,
        completed_generation=0, next_attempt_at=now, created_at=now, updated_at=now,
    )
    return (await db.execute(statement.on_conflict_do_update(
        index_elements=[column, 'policy_id'], set_={
            'requested_generation': MatchEvaluationJob.requested_generation + 1,
            'failed_at': None, 'last_error_code': None, 'next_attempt_at': now,
            'attempts': case(
                (MatchEvaluationJob.failed_at.is_not(None), 0),
                else_=MatchEvaluationJob.attempts,
            ),
            'updated_at': now,
        },
    ).returning(MatchEvaluationJob.id))).scalar_one()


async def _request(db, owner, now, *, analyze):
    if not db.in_transaction():
        raise RuntimeError('Analysis requests require a caller-owned transaction')
    if not eligible(owner, now):
        return None
    policy, profile = await active_policy(db)
    if not analyze:
        return await enqueue_reevaluation(db, owner=owner, policy_id=policy.id, now=now)

    event_type = next(key for key, value in KINDS.items() if isinstance(owner, value[0]))
    _, feature_model, column, payload_key = KINDS[event_type]
    if 'text_version' in inspect(owner).expired_attributes:
        await db.refresh(owner, attribute_names=['text_version'])
    value = analysis_input(owner)
    statement = insert(feature_model).values(
        **{column: owner.id}, profile_id=profile.id, text_version=owner.text_version,
        source_hash=value.source_hash,
        source_language=source_language('\n'.join(filter(None, (value.title, value.description)))),
        status='PENDING', created_at=now, updated_at=now,
    ).on_conflict_do_nothing(index_elements=[column, 'profile_id', 'text_version'])
    await db.execute(statement)
    feature = (await db.execute(select(feature_model).where(
        getattr(feature_model, column) == owner.id, feature_model.profile_id == profile.id,
        feature_model.text_version == owner.text_version,
    ))).scalar_one()
    if feature.status in {'PENDING', 'PROCESSING'}:
        await db.execute(insert(OutboxEvent).values(
            event_type=event_type, aggregate_id=feature.id, aggregate_version=1,
            payload={'featureId': str(feature.id), payload_key: str(owner.id),
                     'profileId': str(profile.id), 'textVersion': owner.text_version},
            created_at=now, next_attempt_at=now,
        ).on_conflict_do_nothing(
            index_elements=['aggregate_id', 'aggregate_version', 'event_type'],
        ))
    await enqueue_reevaluation(db, owner=owner, policy_id=policy.id, now=now)
    return feature


async def request_found_item_analysis(db, *, item, now):
    return await _request(db, item, now, analyze=True)


async def request_lost_report_analysis(db, *, report, now):
    return await _request(db, report, now, analyze=True)


async def request_item_reevaluation(db, *, item, now):
    return await _request(db, item, now, analyze=False)


async def request_report_reevaluation(db, *, report, now):
    return await _request(db, report, now, analyze=False)


async def analysis_status(db, *, owner):
    """Read-only current-profile status; never creates work or runs inference."""
    if 'text_version' in inspect(owner).expired_attributes:
        await db.refresh(owner, attribute_names=['text_version'])
    _, feature_model, column, _ = next(value for value in KINDS.values() if isinstance(owner, value[0]))
    query = select(feature_model.status).where(
        getattr(feature_model, column) == owner.id,
        feature_model.text_version == owner.text_version,
    )
    if isinstance(owner, LostReport) and owner.status != 'OPEN':
        # Closed reports retain their last analysis across later profile changes.
        query = query.order_by(feature_model.created_at.desc(), feature_model.id.desc()).limit(1)
    else:
        _, profile = await active_policy(db)
        query = query.where(feature_model.profile_id == profile.id)
    status = (await db.execute(query)).scalar_one_or_none()
    return status if status in {'PENDING', 'PROCESSING', 'READY', 'FAILED'} else 'PENDING'
