"""Blocking backup operations; run from the dedicated worker thread or CLI."""

from datetime import datetime, time, timedelta, timezone
import hashlib
import logging
import os
from pathlib import Path
import subprocess
import tempfile
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from minio.error import S3Error

from library.database import database_url
from library.photo_storage import PhotoStorage, StorageSettings


logger = logging.getLogger(__name__)
LOCK_KEY = 73011911


def utcnow():
    return datetime.now(timezone.utc)


def due_date(settings, now, startup):
    local = now.astimezone(ZoneInfo(settings.timezone))
    scheduled = datetime.combine(local.date(), time.fromisoformat(settings.time), local.tzinfo)
    if local < scheduled:
        return None
    if not settings.catch_up_enabled and startup > scheduled:
        return None
    return local.date()


class DatabaseBackupService:
    def __init__(self, settings, *, url=None, storage=None, clock=utcnow):
        self.settings = settings
        self.url = url or database_url()
        self.clock = clock
        config = StorageSettings.from_env()
        if settings.minio_bucket == config.bucket:
            raise ValueError('Backup bucket must differ from the photo bucket')
        self.storage = storage or PhotoStorage(config)
        self.client = self.storage.client
        self.bucket = settings.minio_bucket
        # Isolate databases even when sharing a bucket (including test databases).
        database_hash = hashlib.sha256(self.url.database.encode()).hexdigest()[:16]
        self.prefix = f'{settings.minio_prefix}{database_hash}/'

    def connect(self):
        return psycopg.connect(
            self.url.set(drivername='postgresql').render_as_string(hide_password=False),
            autocommit=True, row_factory=dict_row, connect_timeout=10,
        )

    def check_bucket(self):
        if not self.client.bucket_exists(self.bucket):
            try:
                self.client.make_bucket(self.bucket)
            except S3Error as error:
                if error.code != 'BucketAlreadyOwnedByYou':
                    raise
        # Refuse public buckets; never modify an existing bucket's policy silently.
        try:
            self.client.get_bucket_policy(self.bucket)
        except S3Error as error:
            if error.code != 'NoSuchBucketPolicy':
                raise
        else:
            raise ValueError('Backup bucket must have no public access policy')
        if self.client.get_bucket_versioning(self.bucket).status in ('Enabled', 'Suspended'):
            raise ValueError('Backup bucket versioning must be disabled for retention deletion')

    def existing(self, key):
        try:
            return self.client.stat_object(self.bucket, key)
        except S3Error as error:
            if error.code in ('NoSuchKey', 'NoSuchObject'):
                return None
            raise

    def archive(self, key):
        env = dict(os.environ)
        env.update({
            'PGHOST': self.url.host or 'db', 'PGPORT': str(self.url.port or 5432),
            'PGUSER': self.url.username or '', 'PGPASSWORD': self.url.password or '',
            'PGDATABASE': self.url.database, 'PGCONNECT_TIMEOUT': '10',
        })
        for name in ('sslmode', 'sslrootcert', 'sslcert', 'sslkey', 'sslcrl', 'channel_binding'):
            if name in self.url.query:
                env[f'PG{name.upper()}'] = self.url.query[name]

        with tempfile.TemporaryDirectory(prefix='kaifind-backup-') as directory:
            archive = Path(directory) / 'database.dump'
            with tempfile.TemporaryFile() as errors:
                subprocess.run(
                    ['pg_dump', '--format=custom', '--no-password', '--file', str(archive)],
                    env=env, stdout=subprocess.DEVNULL, stderr=errors,
                    timeout=self.settings.timeout_seconds, check=True,
                )
                subprocess.run(
                    ['pg_restore', '--list', str(archive)],
                    stdout=subprocess.DEVNULL, stderr=errors,
                    timeout=self.settings.timeout_seconds, check=True,
                )
            with archive.open('rb') as source:
                digest = hashlib.file_digest(source, 'sha256').hexdigest()
            size = archive.stat().st_size
            completed = self.clock().isoformat()
            self.client.fput_object(
                self.bucket, key, str(archive), content_type='application/octet-stream',
                metadata={'sha256': digest, 'completed-at': completed},
            )
            result = self.existing(key)
            if result is None or result.size != size or result.metadata.get('x-amz-meta-sha256') != digest:
                raise RuntimeError('Backup upload verification failed')
            return result

    def cleanup(self):
        cutoff = self.clock() - timedelta(days=self.settings.retention_days)
        for obj in self.client.list_objects(self.bucket, prefix=self.prefix, recursive=True):
            if obj.object_name.endswith('.dump') and obj.last_modified <= cutoff:
                self.client.remove_object(self.bucket, obj.object_name)

    def run_once(self, *, startup=None, manual=False):
        now = self.clock()
        day = now.astimezone(ZoneInfo(self.settings.timezone)).date() if manual else due_date(
            self.settings, now, startup or now,
        )
        if day is None:
            return 'NOT_DUE'

        with self.connect() as db:
            if not db.execute('SELECT pg_try_advisory_lock(%s) AS locked', (LOCK_KEY,)).fetchone()['locked']:
                return 'BUSY'
            row = db.execute('SELECT * FROM database_backups WHERE scheduled_date=%s', (day,)).fetchone()
            if row and row['status'] == 'SUCCEEDED':
                self.check_bucket()
                self.cleanup()
                return 'SUCCEEDED'
            if row and row['status'] == 'RUNNING' and row['attempts'] >= self.settings.max_attempts:
                self.check_bucket()
                result = self.existing(f'{self.prefix}{day.isoformat()}.dump')
                if result is None:
                    db.execute("""UPDATE database_backups SET status='FAILED',
                        last_error_code='BACKUP_INTERRUPTED' WHERE scheduled_date=%s""", (day,))
                    return 'FAILED'
            if row and row['status'] != 'RUNNING':
                if row['attempts'] >= self.settings.max_attempts:
                    return 'FAILED'
                if not manual and row['next_attempt_at'] and row['next_attempt_at'] > now:
                    return 'WAITING'

            # RUNNING without the session lock means the previous process died.
            # Reconcile a completed PUT before incrementing another attempt.
            key = f'{self.prefix}{day.isoformat()}.dump'
            attempts = min((row['attempts'] if row else 0) + 1, self.settings.max_attempts)
            db.execute('''INSERT INTO database_backups
                (scheduled_date, status, attempts, started_at) VALUES (%s, 'RUNNING', %s, %s)
                ON CONFLICT (scheduled_date) DO UPDATE SET status='RUNNING',
                attempts=EXCLUDED.attempts, started_at=EXCLUDED.started_at,
                next_attempt_at=NULL, last_error_code=NULL''', (day, attempts, now))
            try:
                self.check_bucket()
                result = self.existing(key) or self.archive(key)
                digest = result.metadata['x-amz-meta-sha256']
                completed = datetime.fromisoformat(result.metadata['x-amz-meta-completed-at'])
                db.execute('''UPDATE database_backups SET status='SUCCEEDED', completed_at=%s,
                    object_key=%s, sha256=%s, size_bytes=%s WHERE scheduled_date=%s''',
                    (completed, key, digest, result.size, day))
            except Exception:
                delay = self.settings.retry_delays[min(attempts - 1, len(self.settings.retry_delays) - 1)]
                db.execute('''UPDATE database_backups SET status='FAILED',
                    last_error_code='BACKUP_FAILED', next_attempt_at=%s WHERE scheduled_date=%s''',
                    (self.clock() + timedelta(seconds=delay), day))
                logger.error('BACKUP_FAILED date=%s attempt=%s', day, attempts)
                return 'FAILED'

            # Cleanup failure must never turn a valid uploaded backup into a failed dump.
            self.cleanup()
            logger.info('BACKUP_SUCCEEDED date=%s', day)
            return 'SUCCEEDED'
