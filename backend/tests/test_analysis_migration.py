"""Retry-audit schema roundtrip preserves history and refuses lossy downgrade."""
import subprocess
from uuid import uuid4

import psycopg
import pytest

from test_matching_migration import migration_database, migrate


def test_retry_audit_roundtrip_and_history_guard(migration_database):
    url = migration_database
    migrate(url, 'upgrade', '20261108_0007')
    event_id, target = uuid4(), uuid4()
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("""INSERT INTO audit_logs
            (id, actor_type, action, target_type, target_id, metadata, purge_after)
            VALUES (%s, 'SYSTEM', 'TEXT_ANALYSIS_RETRIED', 'FOUND_ITEM', %s,
                    jsonb_build_object('eventId', %s::text), now()+interval '1 year')""",
            (event_id, target, str(uuid4())))
    with pytest.raises(subprocess.CalledProcessError):
        migrate(url, 'downgrade', '20261107_0006')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT action FROM audit_logs WHERE id=%s', (event_id,)).fetchone() == ('TEXT_ANALYSIS_RETRIED',)
        assert db.execute('SELECT version_num FROM alembic_version').fetchone() == ('20261108_0007',)
        db.execute('DELETE FROM audit_logs WHERE id=%s', (event_id,))
    migrate(url, 'downgrade', '20261107_0006')
    migrate(url, 'upgrade', 'head')
