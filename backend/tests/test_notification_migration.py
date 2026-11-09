"""Upgrade/backfill/downgrade without deleting delivery history."""

from datetime import date, time
import subprocess
from uuid import uuid4

import psycopg
import pytest

from test_matching_migration import migration_database, migrate


def test_delivery_policy_backfill_and_roundtrip(migration_database):
    url = migration_database
    migrate(url, 'upgrade', '20261108_0008')
    user_id, delivery_id = uuid4(), uuid4()
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("""INSERT INTO users (id,mock_subject,name,email,affiliation)
            VALUES (%s,%s,'Test','test@example.com','STUDENT')""", (user_id, str(user_id)))
        db.execute("""INSERT INTO email_deliveries
            (id,recipient_id,delivery_date,kind,slot_no,status,provider_message_id,sent_at)
            VALUES (%s,%s,'2026-11-08','INDIVIDUAL',1,'SENT','retained',now())""",
                   (delivery_id, user_id))
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT daily_limit,digest_time FROM email_delivery_policies').fetchone() == (20, time(20))
        assert db.execute('SELECT status,provider_message_id FROM email_deliveries').fetchone() == ('SENT', 'retained')
    migrate(url, 'downgrade', '20261108_0008')
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute('INSERT INTO mock_email_receipts (delivery_id,accepted_at) VALUES (%s,now())', (delivery_id,))
    with pytest.raises(subprocess.CalledProcessError):
        migrate(url, 'downgrade', '20261108_0008')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT delivery_id FROM mock_email_receipts').fetchone() == (delivery_id,)
        assert db.execute('SELECT version_num FROM alembic_version').fetchone() == ('20261109_0010',)
