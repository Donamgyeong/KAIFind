"""Backup history migration round-trip preserves unrelated application tables."""

import psycopg

from test_matching_migration import migration_database, migrate


def test_backup_migration_roundtrip(migration_database):
    url = migration_database
    migrate(url, 'upgrade', '20261109_0010')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("CREATE TABLE backup_migration_marker (id integer PRIMARY KEY)")
        db.execute('INSERT INTO backup_migration_marker VALUES (1)')
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT count(*) FROM database_backups').fetchone() == (0,)
        db.execute("""INSERT INTO database_backups
            (scheduled_date,status,attempts,started_at) VALUES (CURRENT_DATE,'FAILED',1,now())""")
    migrate(url, 'downgrade', '20261109_0010')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute("SELECT to_regclass('database_backups')").fetchone() == (None,)
        assert db.execute('SELECT id FROM backup_migration_marker').fetchone() == (1,)
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT count(*) FROM database_backups').fetchone() == (0,)
        assert db.execute('SELECT id FROM backup_migration_marker').fetchone() == (1,)
