"""Keyword migration preserves existing subscriptions and registration history."""

import subprocess
from uuid import uuid4

import psycopg
import pytest

from test_matching_migration import migration_database, migrate


def test_keyword_upgrade_no_backfill_and_history_guard(migration_database):
    url = migration_database
    migrate(url, 'upgrade', '20261109_0009')
    user, subscription = uuid4(), uuid4()
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("INSERT INTO users (id,mock_subject,name,email,affiliation) VALUES (%s,%s,'Test','test@example.com','STUDENT')",
                   (user, str(user)))
        db.execute("INSERT INTO keyword_subscriptions (id,user_id,keyword,normalized_keyword) VALUES (%s,%s,'wallet','wallet')",
                   (subscription, user))
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT id,keyword FROM keyword_subscriptions').fetchone() == (subscription, 'wallet')
        assert db.execute('SELECT count(*) FROM keyword_registration_events').fetchone() == (0,)
    migrate(url, 'downgrade', '20261109_0009')
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        category, building, item = uuid4(), uuid4(), uuid4()
        db.execute("INSERT INTO categories (id,name_ko,name_en) VALUES (%s,'물품','Item')", (category,))
        db.execute("INSERT INTO buildings (id,code,name_ko,name_en) VALUES (%s,'A','건물','Building')", (building,))
        db.execute("""INSERT INTO found_items
            (id,finder_id,category_id,found_building_id,title,description,found_location_description,found_at,expires_at)
            VALUES (%s,%s,%s,%s,'Item','black wallet','Private',now(),now()+interval '30 days')""",
                   (item, user, category, building))
        row = db.execute('SELECT id,source_description FROM keyword_registration_events').fetchone()
        assert row[1] == 'black wallet'
    with pytest.raises(subprocess.CalledProcessError):
        migrate(url, 'downgrade', '20261109_0009')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone() == ('20261109_0010',)
        assert db.execute('SELECT id FROM keyword_registration_events').fetchone() == (row[0],)
