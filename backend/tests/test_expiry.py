"""Real expiry transactions, races, retry recovery and backup ordering."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, insert, update

from library.expiry import effective_report_status, report_is_open
from library.expiry_settings import ExpirySettings
from library.matching_lock import MATCHING_LOCK_NAMESPACE, category_lock_key
from model import Conversation, FoundItem, LostReport, LostReportPrivateDetail, Message
from service.database_backup import LOCK_KEY
from test_database_backup import backup_service
from test_schema import seed


@pytest.fixture
def data(backup_service):
    service = backup_service
    engine = create_engine(service.url.set(drivername='postgresql+psycopg'))
    report, conversation = uuid4(), uuid4()
    with engine.begin() as db:
        ids = seed.__wrapped__(db)
        db.execute(insert(Conversation).values(
            id=conversation, item_id=ids['item'], member_id=ids['member'],
        ))
        db.execute(insert(Message).values(conversation_id=conversation,
                                         sender_id=ids['member'], content='PRIVATE MESSAGE'))
        db.execute(update(FoundItem).where(FoundItem.id == ids['item']).values(
            expires_at=service.clock(), hidden=True,
        ))
        db.execute(insert(LostReport).values(
            id=report, owner_id=ids['member'], category_id=ids['category'],
            description='Lost', lost_date_from=service.clock().date(),
            lost_date_to=service.clock().date(), expires_at=service.clock(),
        ))
        db.execute(insert(LostReportPrivateDetail).values(report_id=report, details='PRIVATE DETAILS'))
    engine.dispose()
    return SimpleNamespace(service=service, ids=ids, report=report, conversation=conversation)


def run_expiry(service):
    with service.connect() as db:
        db.execute('SELECT pg_advisory_lock(%s)', (LOCK_KEY,))
        return service.expiry.run(db, service.clock().date(), manual=True)


def test_boundary_helpers():
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    report = SimpleNamespace(status='OPEN', expires_at=now)
    assert not report_is_open(report, now)
    assert effective_report_status(report, now) == 'CLOSED'
    assert report.status == 'OPEN'  # Read projection never changes persisted state.
    report.expires_at += timedelta(microseconds=1)
    assert report_is_open(report, now)
    report.status = 'RESOLVED'
    assert effective_report_status(report, now) == 'RESOLVED'


@pytest.mark.parametrize('policy', [
    {'batch_size': 0}, {'max_attempts': 4}, {'retry_seconds': '0,1'},
    {'lock_timeout_seconds': 0}, {'retry_seconds': 'invalid'},
])
def test_invalid_expiry_policy(policy):
    with pytest.raises(ValueError):
        ExpirySettings(**policy)


def test_expiry_deletes_private_data_and_enqueues_once(data):
    service = data.service
    service.expiry.settings = ExpirySettings(batch_size=1)
    notification_id = uuid4()
    with service.connect() as db:
        db.execute('''INSERT INTO notifications
            (id,event_id,recipient_id,type,item_id,report_id,purge_after)
            VALUES (%s,%s,%s,'MATCH_CANDIDATE',%s,%s,%s)''',
            (notification_id, uuid4(), data.ids['member'], data.ids['item'], data.report,
             service.clock() + timedelta(days=365)))
        db.execute('INSERT INTO email_delivery_items (id,notification_id) VALUES (%s,%s)',
                   (uuid4(), notification_id))

    result = run_expiry(service)
    assert (result['status'], result['expired_items'], result['closed_reports']) == ('SUCCEEDED', 1, 1)
    assert run_expiry(service)['attempts'] == 1
    with service.connect() as db:
        item = db.execute('SELECT * FROM found_items WHERE id=%s', (data.ids['item'],)).fetchone()
        assert item['status'] == 'EXPIRED' and item['hidden']
        assert item['closed_at'] == service.clock()
        assert item['purge_after'].year == service.clock().year + 1
        assert db.execute('SELECT count(*) AS n FROM messages').fetchone()['n'] == 0
        assert db.execute('SELECT count(*) AS n FROM lost_report_private_details').fetchone()['n'] == 0
        assert db.execute('SELECT status FROM email_delivery_items').fetchone()['status'] == 'CANCELLED'
        assert db.execute("SELECT count(*) AS n FROM outbox_events WHERE event_type='EXPIRY_NOTIFICATION'").fetchone()['n'] == 1
        audit = db.execute('SELECT actor_type,actor_id,metadata FROM audit_logs').fetchall()
        assert len(audit) == 2 and all(row['actor_type'] == 'SYSTEM' and row['actor_id'] is None for row in audit)


@pytest.mark.parametrize('change', ['future', 'deleted', 'collected'])
def test_ineligible_items_and_extended_report_are_preserved(data, change):
    service = data.service
    with service.connect() as db:
        if change == 'future':
            db.execute('UPDATE found_items SET expires_at=%s WHERE id=%s',
                       (service.clock() + timedelta(microseconds=1), data.ids['item']))
        elif change == 'deleted':
            db.execute('UPDATE found_items SET deleted_at=%s WHERE id=%s', (service.clock(), data.ids['item']))
        else:
            db.execute("UPDATE found_items SET status='COLLECTED',closed_at=%s WHERE id=%s",
                       (service.clock(), data.ids['item']))
        db.execute('UPDATE lost_reports SET expires_at=%s WHERE id=%s',
                   (service.clock() + timedelta(days=30), data.report))
    result = run_expiry(service)
    assert result['expired_items'] == result['closed_reports'] == 0
    with service.connect() as db:
        assert db.execute('SELECT details FROM lost_report_private_details').fetchone()['details'] == 'PRIVATE DETAILS'


def test_atomic_rollback_and_retry_limit_blocks_backup(data, monkeypatch):
    service = data.service
    original = service.expiry.close
    def fail_after_write(*args):
        original(*args)
        raise RuntimeError('simulated failure after state and privacy changes')
    monkeypatch.setattr(service.expiry, 'close', fail_after_write)
    assert service.run_once(manual=True) == 'EXPIRY_BLOCKED'
    with service.connect() as db:
        assert db.execute('SELECT status FROM found_items').fetchone()['status'] == 'POSTED'
        assert db.execute('SELECT count(*) AS n FROM messages').fetchone()['n'] == 1
        assert db.execute('SELECT count(*) AS n FROM audit_logs').fetchone()['n'] == 0
        assert db.execute('SELECT count(*) AS n FROM database_backups').fetchone()['n'] == 0
    assert service.run_once() == 'EXPIRY_BLOCKED'
    with service.connect() as db:
        assert db.execute('SELECT attempts FROM daily_expiry_runs').fetchone()['attempts'] == 1
    for _ in range(4):
        service.run_once(manual=True)
    with service.connect() as db:
        assert db.execute('SELECT attempts FROM daily_expiry_runs').fetchone()['attempts'] == 3
    assert not service.client.bucket_exists(service.bucket)


def test_category_lock_timeout_and_resume(data):
    service = data.service
    service.expiry.settings = ExpirySettings(lock_timeout_seconds=1)
    with service.connect() as blocker:
        blocker.execute('SELECT pg_advisory_lock(%s,%s)',
                        (MATCHING_LOCK_NAMESPACE, category_lock_key(data.ids['category'])))
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(service.run_once, manual=True).result(timeout=5) == 'EXPIRY_BLOCKED'
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        expiry = db.execute('SELECT * FROM daily_expiry_runs').fetchone()
        backup = db.execute('SELECT * FROM database_backups').fetchone()
        assert expiry['attempts'] == 2
        assert backup['expiry_run_id'] == expiry['run_id']
        assert expiry['completed_at'] <= backup['completed_at']


def test_partial_batch_recovery_and_backup_retry(data, monkeypatch):
    service = data.service
    service.expiry.settings = ExpirySettings(batch_size=1)
    original_close = service.expiry.close
    def fail_report(db, table, *args):
        if table == 'lost_reports':
            raise RuntimeError('report batch failed')
        original_close(db, table, *args)
    monkeypatch.setattr(service.expiry, 'close', fail_report)
    assert service.run_once(manual=True) == 'EXPIRY_BLOCKED'
    with service.connect() as db:
        assert db.execute('SELECT expired_items FROM daily_expiry_runs').fetchone()['expired_items'] == 1
    monkeypatch.setattr(service.expiry, 'close', original_close)
    archive = service.archive
    def failed_dump(key):
        raise RuntimeError('backup failed')
    monkeypatch.setattr(service, 'archive', failed_dump)
    assert service.run_once(manual=True) == 'FAILED'
    monkeypatch.setattr(service, 'archive', archive)
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        run = db.execute('SELECT * FROM daily_expiry_runs').fetchone()
        assert (run['expired_items'], run['closed_reports'], run['attempts']) == (1, 1, 2)
        assert db.execute('SELECT count(*) AS n FROM audit_logs').fetchone()['n'] == 2


def test_legacy_backup_requires_new_archive_after_expiry(data):
    service = data.service
    day = service.clock().date()
    with service.connect() as db:
        db.execute("""INSERT INTO database_backups
            (scheduled_date,status,attempts,started_at,completed_at,object_key)
            VALUES (%s,'SUCCEEDED',1,%s,%s,'legacy.dump')""", (day, service.clock(), service.clock()))
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        row = db.execute('SELECT * FROM database_backups').fetchone()
        assert row['expiry_run_id'] is not None and row['object_key'] != 'legacy.dump'
    assert service.existing(row['object_key']) is not None


@pytest.mark.parametrize('operation', ['collect', 'extend', 'repost', 'message'])
def test_concurrent_writer_is_rechecked_without_residual_messages(data, operation):
    import time
    service = data.service
    with ThreadPoolExecutor(max_workers=1) as pool:
        with service.connect() as writer:
            with writer.transaction():
                if operation != 'message':
                    writer.execute('SELECT pg_advisory_xact_lock(%s,%s)',
                                   (MATCHING_LOCK_NAMESPACE, category_lock_key(data.ids['category'])))
                writer.execute('SELECT id FROM found_items WHERE id=%s FOR UPDATE', (data.ids['item'],))
                future = pool.submit(service.run_once, manual=True)
                waiting = False
                for _ in range(200):
                    waiting = writer.execute('''SELECT EXISTS (
                        SELECT 1 FROM pg_locks l JOIN pg_stat_activity a USING (pid)
                        WHERE a.datname=current_database() AND NOT l.granted
                    ) AS waiting''').fetchone()['waiting']
                    if waiting:
                        break
                    time.sleep(0.01)
                assert waiting
                if operation == 'collect':
                    writer.execute("UPDATE found_items SET status='COLLECTED',closed_at=%s WHERE id=%s",
                                   (service.clock(), data.ids['item']))
                elif operation == 'extend':
                    writer.execute('UPDATE lost_reports SET expires_at=%s WHERE id=%s',
                                   (service.clock() + timedelta(days=30), data.report))
                elif operation == 'repost':
                    writer.execute('UPDATE found_items SET posted_at=%s,expires_at=%s WHERE id=%s',
                                   (service.clock(), service.clock() + timedelta(days=30), data.ids['item']))
                else:
                    writer.execute('''INSERT INTO messages (id,conversation_id,sender_id,content)
                        VALUES (%s,%s,%s,'concurrent message')''',
                        (uuid4(), data.conversation, data.ids['member']))
            assert future.result(timeout=10) == 'SUCCEEDED'
    with service.connect() as db:
        row = db.execute('SELECT * FROM daily_expiry_runs').fetchone()
        assert row['expired_items'] == (0 if operation in ('collect', 'repost') else 1)
        assert row['closed_reports'] == (0 if operation == 'extend' else 1)
        if operation != 'repost':
            assert db.execute('SELECT count(*) AS n FROM messages').fetchone()['n'] == 0


def test_restore_contains_expiry_and_redaction(data, tmp_path):
    import hashlib
    import os
    import psycopg
    import subprocess
    service = data.service
    assert service.run_once(manual=True) == 'SUCCEEDED'
    with service.connect() as db:
        row = db.execute('SELECT * FROM database_backups').fetchone()
    archive = tmp_path / 'expired.dump'
    service.client.fget_object(service.bucket, row['object_key'], str(archive))
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == row['sha256']
    restore = service.restore_url
    subprocess.run([
        'pg_restore', '--exit-on-error', '--no-owner', '--no-acl',
        '--host', restore.host, '--port', str(restore.port or 5432),
        '--username', restore.username, '--dbname', restore.database, str(archive),
    ], env=dict(os.environ, PGPASSWORD=restore.password), capture_output=True, check=True)
    with psycopg.connect(restore.render_as_string(hide_password=False)) as db:
        assert db.execute('SELECT status FROM found_items').fetchone() == ('EXPIRED',)
        assert db.execute('SELECT status FROM lost_reports').fetchone() == ('CLOSED',)
        assert db.execute('SELECT count(*) FROM lost_report_private_details').fetchone() == (0,)
        assert db.execute('SELECT count(*) FROM messages').fetchone() == (0,)
        assert db.execute('SELECT status FROM daily_expiry_runs').fetchone() == ('SUCCEEDED',)
