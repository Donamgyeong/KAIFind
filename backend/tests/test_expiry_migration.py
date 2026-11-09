"""Daily expiry migration preserves existing backup history across a round-trip."""

import psycopg

from test_matching_migration import migration_database, migrate


def test_daily_expiry_migration_preserves_backups(migration_database):
    url = migration_database
    migrate(url, 'upgrade', '20261109_0011')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        db.execute("""INSERT INTO database_backups
            (scheduled_date,status,attempts,started_at,object_key)
            VALUES (CURRENT_DATE,'SUCCEEDED',1,now(),'legacy.dump')""")
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT object_key,expiry_run_id FROM database_backups').fetchone() == ('legacy.dump', None)
        assert db.execute('SELECT count(*) FROM daily_expiry_runs').fetchone() == (0,)
    migrate(url, 'downgrade', '20261109_0011')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT object_key FROM database_backups').fetchone() == ('legacy.dump',)
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT object_key FROM database_backups').fetchone() == ('legacy.dump',)
