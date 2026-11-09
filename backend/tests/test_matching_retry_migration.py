"""Matching retry audit migration is reversible only without retained new history."""
import subprocess
from uuid import uuid4

import psycopg
import pytest

from test_matching_migration import migration_database, migrate


def test_matching_retry_audit_preserved_on_downgrade(migration_database):
    url = migration_database
    migrate(url, 'upgrade', 'head')
    key = uuid4()
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("""INSERT INTO audit_logs
            (id, actor_type, action, target_type, target_id, metadata, purge_after)
            VALUES (%s, 'SYSTEM', 'MATCH_EVALUATION_RETRIED', 'LOST_REPORT', %s,
                    jsonb_build_object('eventId', %s::text), now()+interval '1 year')""",
                   (key, uuid4(), str(uuid4())))
    with pytest.raises(subprocess.CalledProcessError):
        migrate(url, 'downgrade', '20261108_0007')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone() == ('20261109_0011',)
        assert db.execute('SELECT action FROM audit_logs WHERE id=%s', (key,)).fetchone() == ('MATCH_EVALUATION_RETRIED',)
        db.execute('DELETE FROM audit_logs WHERE id=%s', (key,))
    migrate(url, 'downgrade', '20261108_0007')
    migrate(url, 'upgrade', 'head')
