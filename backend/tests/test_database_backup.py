"""Real pg_dump/MinIO/restore checks using isolated databases and buckets."""

from datetime import datetime, timedelta, timezone
import hashlib
import os
import subprocess
from uuid import uuid4

import psycopg
from psycopg import sql
import pytest
from sqlalchemy.engine import make_url

from library.backup_settings import BackupSettings
from library.photo_storage import PhotoStorage, StorageSettings
from service.database_backup import DatabaseBackupService, due_date
from test_matching_migration import migrate


@pytest.mark.parametrize('name,value', [
    ('BACKUP_TIME', '4:00'), ('BACKUP_TIME', '24:00'),
    ('BACKUP_RETENTION_DAYS', '0'), ('BACKUP_MAX_ATTEMPTS', '4'),
    ('BACKUP_RETRY_SECONDS', '0,300'), ('BACKUP_MINIO_PREFIX', '../photos/'),
])
def test_invalid_policy(monkeypatch, name, value):
    monkeypatch.setenv(name, value)
    with pytest.raises(ValueError):
        BackupSettings()


def test_due_time_and_catchup():
    settings = BackupSettings()
    before = datetime(2026, 11, 8, 18, 59, tzinfo=timezone.utc)
    boundary = before + timedelta(minutes=1)
    assert due_date(settings, before, before) is None
    assert due_date(settings, boundary, before).isoformat() == '2026-11-09'
    late = boundary + timedelta(hours=2)
    assert due_date(settings, late, late) is not None
    assert due_date(settings.model_copy(update={'catch_up_enabled': False}), late, late) is None
    assert due_date(settings.model_copy(update={'catch_up_enabled': False}), late, before) is not None


@pytest.mark.asyncio
async def test_worker_shutdown():
    import asyncio
    from service.backup_worker import BackupWorker

    class Service:
        settings = BackupSettings(poll_seconds=1)
        calls = 0

        def run_once(self, **kwargs):
            self.calls += 1

    service = Service()
    worker = BackupWorker(service)
    worker.start()
    for _ in range(100):
        if service.calls:
            break
        await asyncio.sleep(0.01)
    await worker.close()
    assert service.calls == 1


@pytest.fixture
def backup_service(tmp_path):
    raw = os.getenv('TEST_DATABASE_URL')
    if not raw:
        pytest.skip('Run through scripts.test_backend')
    base = make_url(raw).set(drivername='postgresql')
    if not base.database.startswith('kaifind_test_'):
        raise RuntimeError('Disposable test database required')
    suffix = uuid4().hex[:16]
    names = [f'kaifind_test_backup_{suffix}', f'kaifind_test_restore_{suffix}']
    admin_url = base.set(database='postgres').render_as_string(hide_password=False)
    with psycopg.connect(admin_url, autocommit=True) as admin:
        for name in names:
            admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    url = base.set(database=names[0])
    migrate(url, 'upgrade', 'head')
    with psycopg.connect(url.render_as_string(hide_password=False), autocommit=True) as db:
        db.execute('CREATE TABLE backup_marker (id integer PRIMARY KEY, value text NOT NULL)')
        db.execute("INSERT INTO backup_marker VALUES (1, 'restore-proof')")
    bucket = f'kaifind-test-backup-{suffix}'
    storage = PhotoStorage(StorageSettings.from_env())
    config = BackupSettings(minio_bucket=bucket)
    now = [datetime(2026, 11, 9, 0, tzinfo=timezone.utc)]
    service = DatabaseBackupService(config, url=url, storage=storage, clock=lambda: now[0])
    service.test_now = now
    service.restore_url = base.set(database=names[1])
    try:
        yield service
    finally:
        if storage.client.bucket_exists(bucket):
            for obj in storage.client.list_objects(bucket, recursive=True):
                storage.client.remove_object(bucket, obj.object_name)
            storage.client.remove_bucket(bucket)
        with psycopg.connect(admin_url, autocommit=True) as admin:
            for name in names:
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


def test_actual_dump_upload_restore_and_idempotency(backup_service, tmp_path):
    service = backup_service
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        row = db.execute('SELECT * FROM database_backups').fetchone()
    assert row['status'] == 'SUCCEEDED'
    assert row['attempts'] == 1
    archive = tmp_path / 'backup.dump'
    service.client.fget_object(service.bucket, row['object_key'], str(archive))
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == row['sha256']
    assert archive.stat().st_size == row['size_bytes']
    env = dict(os.environ, PGPASSWORD=service.restore_url.password)
    subprocess.run([
        'pg_restore', '--exit-on-error', '--no-owner', '--no-acl',
        '--host', service.restore_url.host, '--port', str(service.restore_url.port or 5432),
        '--username', service.restore_url.username, '--dbname', service.restore_url.database,
        str(archive),
    ], env=env, check=True, capture_output=True)
    with psycopg.connect(service.restore_url.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT value FROM backup_marker WHERE id=1').fetchone() == ('restore-proof',)
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        assert db.execute('SELECT attempts FROM database_backups').fetchone()['attempts'] == 1


def test_failure_retry_limit_and_no_partial_success(backup_service, monkeypatch):
    service = backup_service
    def fail(key):
        raise RuntimeError('simulated dump failure')
    monkeypatch.setattr(service, 'archive', fail)
    assert service.run_once(manual=True) == 'FAILED'
    assert service.run_once() == 'WAITING'
    for attempt in (2, 3):
        service.test_now[0] += timedelta(seconds=301)
        assert service.run_once() == 'FAILED'
    service.test_now[0] += timedelta(seconds=301)
    assert service.run_once() == 'FAILED'
    with service.connect() as db:
        row = db.execute('SELECT * FROM database_backups').fetchone()
        assert row['attempts'] == 3
        assert row['completed_at'] is None
        assert row['object_key'] is None
    assert not list(service.client.list_objects(service.bucket, prefix=service.prefix))


def test_lock_and_crash_after_upload_reconciliation(backup_service, monkeypatch):
    service = backup_service
    with service.connect() as db:
        db.execute('SELECT pg_advisory_lock(73011911)')
        assert service.run_once(manual=True) == 'BUSY'
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        db.execute("UPDATE database_backups SET status='RUNNING', completed_at=NULL, attempts=3")
    def unexpected(key):
        pytest.fail('Uploaded archive must be reconciled without a second dump')
    monkeypatch.setattr(service, 'archive', unexpected)
    assert service.run_once(manual=True) == 'SUCCEEDED'


def test_retention_boundary_and_prefix_isolation(backup_service):
    service = backup_service
    assert service.run_once(manual=True) == 'SUCCEEDED'
    objects = list(service.client.list_objects(service.bucket, prefix=service.prefix))
    key, uploaded = objects[0].object_name, objects[0].last_modified
    from io import BytesIO
    unrelated = 'unrelated/photo.dump'
    service.client.put_object(service.bucket, unrelated, BytesIO(b'x'), 1)
    service.test_now[0] = uploaded + timedelta(days=7, microseconds=-1)
    service.cleanup()
    assert service.existing(key) is not None
    service.test_now[0] += timedelta(microseconds=1)
    service.cleanup()
    assert service.existing(key) is None
    assert service.existing(unrelated) is not None


def test_public_bucket_is_refused(backup_service):
    import json
    service = backup_service
    service.check_bucket()
    service.client.set_bucket_policy(service.bucket, json.dumps({
        'Version': '2012-10-17', 'Statement': [{
            'Effect': 'Allow', 'Principal': {'AWS': ['*']}, 'Action': ['s3:GetObject'],
            'Resource': [f'arn:aws:s3:::{service.bucket}/*'],
        }],
    }))
    assert service.run_once(manual=True) == 'FAILED'
    assert not list(service.client.list_objects(service.bucket))
