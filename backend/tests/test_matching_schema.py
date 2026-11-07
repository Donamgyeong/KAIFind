"""Real PostgreSQL constraints and fencing primitives for asynchronous matching."""
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import delete, insert, select, text, update
from sqlalchemy.exc import IntegrityError

from model import (
    FoundItem, FoundItemTextFeature, LostReport, LostReportTextFeature,
    MatchCandidate, MatchEvaluationJob, MatchingPolicy, MatchingRuntime,
    OutboxEvent, TextAnalysisProfile,
)
from test_schema import NOW, db, engine, report, seed


@pytest.fixture
def policy(db):
    profile_id, policy_id = uuid4(), uuid4()
    db.execute(insert(TextAnalysisProfile).values(
        id=profile_id, name=str(profile_id),
        model_name='Helsinki-NLP/opus-mt_tiny_kor-eng',
        model_revision='a' * 40, tokenizer_revision='a' * 40,
        input_format_version='v1', language_rule_version='v1', keyword_rule_version='v1',
        runtime_config={}, fingerprint=profile_id.hex * 2,
    ))
    db.execute(insert(MatchingPolicy).values(
        id=policy_id, analysis_profile_id=profile_id, rule_version='v1',
        config={'reason': 'building_or_keyword'}, fingerprint=policy_id.hex * 2,
    ))
    return profile_id, policy_id


def feature_values(profile_id):
    return dict(id=uuid4(), profile_id=profile_id, text_version=1,
                source_hash='b' * 64, source_language='KO')


def ready_values():
    return dict(status='READY', translated_text='black wallet',
                keywords=['color:black', 'object:wallet'], attributes={}, completed_at=NOW)


def make_report(db, seed):
    from model import LostReportPrivateDetail

    rid = report(db, seed)
    db.execute(insert(LostReportPrivateDetail).values(report_id=rid, details='Private mark'))
    return rid


@pytest.mark.parametrize('field', ['description', 'title'])
def test_item_text_version_changes_only_for_model_input(db, seed, field):
    target = FoundItem.id == seed['item']
    assert db.execute(select(FoundItem.text_version).where(target)).scalar_one() == 1
    db.execute(update(FoundItem).where(target).values({field: 'Changed', 'text_version': 900}))
    assert db.execute(select(FoundItem.text_version).where(target)).scalar_one() == 2
    db.execute(update(FoundItem).where(target).values({field: 'Changed', 'text_version': 901}))
    db.execute(update(FoundItem).where(target).values(found_location_description='Desk'))
    assert db.execute(select(FoundItem.text_version).where(target)).scalar_one() == 2


def test_report_text_version_ignores_non_input_and_manual_changes(db, seed):
    rid = make_report(db, seed)
    target = LostReport.id == rid
    db.execute(update(LostReport).where(target).values(text_version=999))
    assert db.execute(select(LostReport.text_version).where(target)).scalar_one() == 1
    db.execute(update(LostReport).where(target).values(description='Different'))
    assert db.execute(select(LostReport.text_version).where(target)).scalar_one() == 2


def test_orm_reads_trigger_generated_text_version_after_flush(db, seed):
    from sqlalchemy.orm import Session

    with Session(bind=db, join_transaction_mode='create_savepoint') as session:
        item = session.get(FoundItem, seed['item'])
        assert item.text_version == 1
        item.title = 'Changed through ORM'
        session.flush()
        assert item.text_version == 2


@pytest.mark.parametrize('model', [TextAnalysisProfile, MatchingPolicy])
def test_profiles_and_policies_are_immutable(db, policy, model):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(model).values(fingerprint='c' * 64))


def test_profile_requires_pinned_revision(db, policy):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(TextAnalysisProfile).from_select(
            ['id', 'name', 'model_name', 'model_revision', 'tokenizer_revision',
             'input_format_version', 'language_rule_version', 'keyword_rule_version',
             'runtime_config', 'fingerprint'],
            select(text("gen_random_uuid(), 'unpinned', model_name, 'main', tokenizer_revision, "
                        "input_format_version, language_rule_version, keyword_rule_version, "
                        "runtime_config, repeat('d', 64)")).select_from(TextAnalysisProfile),
        ))


def test_runtime_singleton_and_generation_are_controlled(db, policy):
    profile_id, policy_id = policy
    db.execute(insert(MatchingRuntime).values(id=1, active_policy_id=policy_id))
    db.execute(update(MatchingRuntime).values(generation=999))
    assert db.execute(select(MatchingRuntime.generation)).scalar_one() == 1
    other = uuid4()
    db.execute(insert(MatchingPolicy).values(
        id=other, analysis_profile_id=profile_id, rule_version='v2', config={}, fingerprint=other.hex * 2,
    ))
    db.execute(update(MatchingRuntime).values(active_policy_id=other))
    assert db.execute(select(MatchingRuntime.generation)).scalar_one() == 2
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(MatchingRuntime).values(id=2, active_policy_id=policy_id))


@pytest.mark.parametrize('bad', [
    {'status': 'READY'},
    {'status': 'FAILED', 'completed_at': NOW},
    {'keywords': ['object:wallet']},
    {**ready_values(), 'keywords': [None]},
    {**ready_values(), 'keywords': ['object:wallet', 'object:wallet']},
    {**ready_values(), 'keywords': ['object:wallet', 'color:black']},
    {**ready_values(), 'keywords': ['']},
    {**ready_values(), 'attributes': []},
])
def test_feature_rejects_inconsistent_results(db, seed, policy, bad):
    values = feature_values(policy[0])
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(FoundItemTextFeature).values(item_id=seed['item'], **{**values, **bad}))


def test_empty_keywords_are_ready_and_results_are_immutable(db, seed, policy):
    values = {**feature_values(policy[0]), **ready_values(), 'keywords': []}
    db.execute(insert(FoundItemTextFeature).values(item_id=seed['item'], **values))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(FoundItemTextFeature).values(translated_text='Changed'))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(FoundItemTextFeature).values(item_id=seed['item'], **{**values, 'id': uuid4()}))


def test_pending_feature_input_identity_is_immutable(db, seed, policy):
    db.execute(insert(FoundItemTextFeature).values(item_id=seed['item'], **feature_values(policy[0])))
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(update(FoundItemTextFeature).values(text_version=2))


def test_new_keyword_candidates_require_correct_owner_profile_and_evidence(db, seed, policy):
    profile_id, policy_id = policy
    rid = make_report(db, seed)
    item_feature, report_feature = feature_values(profile_id), feature_values(profile_id)
    db.execute(insert(FoundItemTextFeature).values(item_id=seed['item'], **item_feature, **ready_values()))
    db.execute(insert(LostReportTextFeature).values(report_id=rid, **report_feature, **ready_values()))
    values = dict(
        id=uuid4(), report_id=rid, item_id=seed['item'], keyword_matched=True,
        policy_id=policy_id, analysis_profile_id=profile_id,
        evaluated_item_version=1, evaluated_report_version=1,
        item_feature_id=item_feature['id'], report_feature_id=report_feature['id'],
        common_keywords=['object:wallet'],
    )
    for bad in ({'common_keywords': []}, {'item_feature_id': None},
                {'evaluated_report_version': None}, {'analysis_profile_id': uuid4()},
                {'report_feature_id': uuid4()}):
        with pytest.raises(IntegrityError), db.begin_nested():
            db.execute(insert(MatchCandidate).values(**{**values, **bad}))
            db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    db.execute(insert(MatchCandidate).values(**values))
    db.execute(text('SET CONSTRAINTS ALL IMMEDIATE'))
    db.execute(delete(FoundItem).where(FoundItem.id == seed['item']))
    assert db.execute(select(MatchCandidate.id)).first() is None
    assert db.execute(select(FoundItemTextFeature.id)).first() is None


def test_legacy_candidate_and_first_notification_survive_upgrade_shape(db, seed):
    rid = make_report(db, seed)
    cid = uuid4()
    db.execute(insert(MatchCandidate).values(
        id=cid, report_id=rid, item_id=seed['item'], keyword_matched=True, first_notified_at=NOW,
    ))
    assert db.execute(select(MatchCandidate.first_notified_at).where(MatchCandidate.id == cid)).scalar_one() == NOW


@pytest.mark.parametrize('bad', [
    {'lease_until': NOW}, {'lease_token': uuid4()},
    {'processed_at': NOW, 'failed_at': NOW},
    {'cancelled_at': NOW, 'lease_token': uuid4(), 'lease_until': NOW},
])
def test_outbox_rejects_invalid_lease_and_terminal_states(db, bad):
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(OutboxEvent).values(
            id=uuid4(), event_type='TEST', aggregate_id=uuid4(), aggregate_version=1, payload={}, **bad,
        ))


@pytest.mark.parametrize('logical', [True, False])
def test_item_delete_erases_features_and_cancels_leased_analysis(db, seed, policy, logical):
    values = feature_values(policy[0])
    db.execute(insert(FoundItemTextFeature).values(item_id=seed['item'], **values))
    eid = uuid4()
    db.execute(insert(OutboxEvent).values(
        id=eid, event_type='FOUND_ITEM_TEXT_ANALYSIS_REQUESTED', aggregate_id=values['id'],
        aggregate_version=1, payload={'featureId': str(values['id'])},
        lease_token=uuid4(), lease_until=NOW + timedelta(minutes=1),
    ))
    db.execute(insert(MatchEvaluationJob).values(item_id=seed['item'], policy_id=policy[1]))
    if logical:
        db.execute(update(FoundItem).where(FoundItem.id == seed['item']).values(deleted_at=NOW))
    else:
        db.execute(delete(FoundItem).where(FoundItem.id == seed['item']))
    event = db.execute(select(OutboxEvent.cancelled_at, OutboxEvent.lease_token).where(OutboxEvent.id == eid)).one()
    assert event.cancelled_at is not None and event.lease_token is None
    assert db.execute(select(FoundItemTextFeature.id)).first() is None
    assert db.execute(select(MatchEvaluationJob.id)).first() is None


@pytest.mark.parametrize('bad', [
    {'requested_generation': 0}, {'completed_generation': 2},
    {'claimed_generation': 1}, {'lease_token': uuid4()},
    {'failed_at': NOW}, {'item_id': None},
])
def test_evaluation_job_rejects_invalid_generation_lease_and_owner(db, seed, policy, bad):
    values = dict(item_id=seed['item'], policy_id=policy[1])
    with pytest.raises(IntegrityError), db.begin_nested():
        db.execute(insert(MatchEvaluationJob).values(**{**values, **bad}))


def test_generation_preserves_request_arriving_during_processing(db, seed, policy):
    jid, token = uuid4(), uuid4()
    db.execute(insert(MatchEvaluationJob).values(
        id=jid, item_id=seed['item'], policy_id=policy[1],
        claimed_generation=1, lease_token=token, lease_until=NOW + timedelta(minutes=5),
    ))
    db.execute(update(MatchEvaluationJob).where(MatchEvaluationJob.id == jid).values(requested_generation=2))
    db.execute(update(MatchEvaluationJob).where(
        MatchEvaluationJob.id == jid, MatchEvaluationJob.lease_token == token,
    ).values(completed_generation=1, claimed_generation=None, lease_token=None, lease_until=None))
    job = db.execute(select(MatchEvaluationJob.requested_generation, MatchEvaluationJob.completed_generation)).one()
    assert job.requested_generation == 2 and job.completed_generation == 1


def test_outbox_skip_locked_and_expired_owner_fencing(engine):
    eid, aggregate, first_token, next_token = [uuid4() for _ in range(4)]
    with engine.begin() as connection:
        connection.execute(insert(OutboxEvent).values(
            id=eid, event_type='FENCING_TEST', aggregate_id=aggregate, aggregate_version=1, payload={},
        ))
    try:
        with engine.connect() as first, engine.connect() as second:
            with first.begin(), second.begin():
                assert first.execute(select(OutboxEvent.id).where(OutboxEvent.id == eid).with_for_update()).scalar_one() == eid
                assert second.execute(select(OutboxEvent.id).where(
                    OutboxEvent.id == eid,
                ).with_for_update(skip_locked=True)).first() is None
        with engine.begin() as connection:
            connection.execute(update(OutboxEvent).where(OutboxEvent.id == eid).values(
                lease_token=first_token, lease_until=NOW - timedelta(seconds=1),
            ))
            connection.execute(update(OutboxEvent).where(OutboxEvent.id == eid).values(
                lease_token=next_token, lease_until=text("now() + interval '1 minute'"),
            ))
            stale = connection.execute(update(OutboxEvent).where(
                OutboxEvent.id == eid, OutboxEvent.lease_token == first_token,
                OutboxEvent.lease_until > text('now()'),
            ).values(processed_at=text('now()'), lease_token=None, lease_until=None))
            assert stale.rowcount == 0
            current = connection.execute(update(OutboxEvent).where(
                OutboxEvent.id == eid, OutboxEvent.lease_token == next_token,
                OutboxEvent.lease_until > text('now()'),
            ).values(processed_at=text('now()'), lease_token=None, lease_until=None))
            assert current.rowcount == 1
    finally:
        with engine.begin() as connection:
            connection.execute(delete(OutboxEvent).where(OutboxEvent.id == eid))


def test_pending_index_excludes_failed_and_cancelled_events(db):
    definition = db.execute(text(
        "SELECT indexdef FROM pg_indexes WHERE indexname='ix_outbox_events_pending'"
    )).scalar_one()
    assert 'failed_at IS NULL' in definition and 'cancelled_at IS NULL' in definition
