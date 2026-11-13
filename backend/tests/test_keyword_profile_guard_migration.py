"""Repair drift without losing registration data or the original guard on downgrade."""

from uuid import uuid4

import psycopg
import pytest
from sqlalchemy import create_engine, insert

from model import MatchingPolicy, MatchingRuntime, TextAnalysisProfile
from service.text_analysis_profiles import POLICY_CONFIG, POLICY_RULE, fingerprint
from test_analysis_worker import PROFILE
from test_matching_migration import migration_database, migrate
from test_schema import seed


@pytest.mark.parametrize('drift', ['function_missing', 'trigger_missing', 'disabled', 'intact'])
def test_restore_guard_preserves_data_and_enforces_drain(migration_database, drift):
    url = migration_database
    migrate(url, 'upgrade', '20261109_0012')
    engine = create_engine(url.set(drivername='postgresql+psycopg'))
    old_policy, new_policy = uuid4(), uuid4()
    try:
        with engine.begin() as db:
            for policy_id, alternate in ((old_policy, False), (new_policy, True)):
                profile_id = uuid4()
                profile = {key: value for key, value in PROFILE.items() if key != 'fingerprint'}
                if alternate:
                    profile['runtime_config'] = {'test': 'alternate'}
                profile['fingerprint'] = fingerprint(profile)
                db.execute(insert(TextAnalysisProfile).values(id=profile_id, name=str(profile_id), **profile))
                db.execute(insert(MatchingPolicy).values(
                    id=policy_id, analysis_profile_id=profile_id, rule_version=POLICY_RULE,
                    config=POLICY_CONFIG, fingerprint=fingerprint({
                        'analysis_profile_fingerprint': profile['fingerprint'],
                        'rule_version': POLICY_RULE, 'config': POLICY_CONFIG,
                    }),
                ))
            db.execute(insert(MatchingRuntime).values(id=1, active_policy_id=old_policy))
            seed.__wrapped__(db)
    finally:
        engine.dispose()

    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        snapshot = db.execute('SELECT to_jsonb(e) FROM keyword_registration_events e').fetchall()
        assert len(snapshot) == 1
        trigger_oid = db.execute("""SELECT oid FROM pg_trigger
            WHERE tgrelid='matching_runtime'::regclass AND tgname='keyword_profile_drain'""").fetchone()[0]
        if drift == 'function_missing':
            db.execute('DROP FUNCTION keyword_profile_drain() CASCADE')
        elif drift == 'trigger_missing':
            db.execute('DROP TRIGGER keyword_profile_drain ON matching_runtime')
        elif drift == 'disabled':
            db.execute('ALTER TABLE matching_runtime DISABLE TRIGGER keyword_profile_drain')

    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT to_jsonb(e) FROM keyword_registration_events e').fetchall() == snapshot
        installed = db.execute("""SELECT oid,tgenabled FROM pg_trigger
            WHERE tgrelid='matching_runtime'::regclass AND tgname='keyword_profile_drain'""").fetchone()
        assert installed[1] == 'O'
        if drift in {'intact', 'disabled'}:
            assert installed[0] == trigger_oid
        # Keeping the current policy is allowed even while events are pending.
        db.execute('UPDATE matching_runtime SET active_policy_id=%s WHERE id=1', (old_policy,))
        with pytest.raises(psycopg.errors.RaiseException, match='Drain keyword registration events'):
            with db.transaction():
                db.execute('UPDATE matching_runtime SET active_policy_id=%s WHERE id=1', (new_policy,))
        assert db.execute('SELECT active_policy_id FROM matching_runtime').fetchone() == (old_policy,)
        db.execute("UPDATE keyword_registration_events SET status='DONE'")
        db.execute('UPDATE matching_runtime SET active_policy_id=%s WHERE id=1', (new_policy,))
        assert db.execute('SELECT active_policy_id FROM matching_runtime').fetchone() == (new_policy,)

    migrate(url, 'downgrade', '20261109_0012')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute("SELECT to_regprocedure('keyword_profile_drain()') IS NOT NULL").fetchone() == (True,)
        assert db.execute('SELECT count(*) FROM keyword_registration_events').fetchone() == (1,)
    migrate(url, 'upgrade', 'head')
