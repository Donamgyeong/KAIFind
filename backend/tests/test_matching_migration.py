"""Upgrade existing semantic metadata without losing candidate history or data.

Uses an additional disposable database in the existing db service; never downgrades
TEST_DATABASE_URL itself or the development database.
"""
import os
import subprocess
import sys
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url


@pytest.fixture
def migration_database():
    raw = os.getenv('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('TEST_DATABASE_URL is required')
    source = make_url(raw)
    if not source.database or not source.database.startswith('kaifind_test_'):
        raise RuntimeError('Migration tests require a separate kaifind_test_* database')
    target = source.set(drivername='postgresql', database=f'kaifind_test_matching_migration_{uuid4().hex}')
    admin_url = target.set(database='postgres').render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(target.database)))
    try:
        yield target
    finally:
        with psycopg.connect(admin_url, autocommit=True) as admin:
            admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(target.database)))


def migrate(url, action, revision):
    env = dict(os.environ, DATABASE_URL=url.render_as_string(hide_password=False))
    subprocess.run([sys.executable, '-m', 'alembic', action, revision],
                   env=env, check=True, capture_output=True, text=True)


def test_existing_embedding_revision_transitions_preserving_versions_and_history(migration_database):
    url = migration_database
    migrate(url, 'upgrade', '20261106_0005')
    finder, category, building, item, report, candidate, event = [uuid4() for _ in range(7)]
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("INSERT INTO users (id,mock_subject,name,email,affiliation) VALUES (%s,%s,'Test','test@example.com','STUDENT')",
                   (finder, str(finder)))
        db.execute("INSERT INTO categories (id,name_ko,name_en) VALUES (%s,'물품','Item')", (category,))
        db.execute("INSERT INTO buildings (id,code,name_ko,name_en) VALUES (%s,'test','건물','Building')", (building,))
        db.execute("""INSERT INTO found_items (id,finder_id,category_id,found_building_id,title,description,
            found_location_description,found_at,expires_at)
            VALUES (%s,%s,%s,%s,'Title','Description','Lobby',now(),now()+interval '30 days')""",
                   (item, finder, category, building))
        db.execute("UPDATE found_items SET description='Changed' WHERE id=%s", (item,))
        db.execute("""INSERT INTO lost_reports (id,owner_id,category_id,description,lost_date_from,lost_date_to,
            status,closed_at,expires_at) VALUES (%s,%s,%s,'Lost',current_date,current_date,
            'CLOSED',now(),now()+interval '30 days')""", (report, finder, category))
        db.execute("""INSERT INTO match_candidates (id,item_id,report_id,semantic_matched,semantic_score,
            item_description_version,report_description_version,item_version,report_version,
            matching_policy_version,first_notified_at)
            VALUES (%s,%s,%s,true,0.91,2,1,1,1,'old-policy',now())""", (candidate, item, report))
        timestamps = db.execute('SELECT matched_at,first_notified_at FROM match_candidates WHERE id=%s', (candidate,)).fetchone()
        db.execute("""INSERT INTO outbox_events (id,event_type,aggregate_id,aggregate_version,payload,lease_token,lease_until)
            VALUES (%s,'LEGACY_TEST',%s,1,'{}',%s,now()+interval '1 hour')""", (event, item, uuid4()))
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT text_version FROM found_items WHERE id=%s', (item,)).fetchone() == (2,)
        row = db.execute('SELECT active,legacy_evidence,matched_at,first_notified_at FROM match_candidates WHERE id=%s', (candidate,)).fetchone()
        assert row[0] is False
        assert row[1]['semantic_score'] == 0.91 and row[1]['matching_policy_version'] == 'old-policy'
        assert row[2:] == timestamps
        assert db.execute('SELECT lease_token,lease_until FROM outbox_events WHERE id=%s', (event,)).fetchone() == (None, None)
        db.execute("UPDATE found_items SET title='New title' WHERE id=%s", (item,))
        assert db.execute('SELECT text_version FROM found_items WHERE id=%s', (item,)).fetchone() == (3,)
    migrate(url, 'downgrade', '20261106_0005')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT description_version FROM found_items WHERE id=%s', (item,)).fetchone() == (3,)
        assert db.execute('SELECT semantic_score,matching_policy_version FROM match_candidates WHERE id=%s', (candidate,)).fetchone() == (0.91, 'old-policy')
    migrate(url, 'upgrade', 'head')
