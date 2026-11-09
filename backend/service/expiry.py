"""Expiry batches under the daily backup session lock, with atomic side effects."""

from datetime import timedelta
import logging
from uuid import uuid4

from psycopg.types.json import Jsonb

from library.matching_lock import MATCHING_LOCK_NAMESPACE, category_lock_key
from service.audit import one_year_after


logger = logging.getLogger(__name__)
TARGETS = (
    ('found_items', "status='POSTED' AND deleted_at IS NULL", 'EXPIRED', 'expired_items'),
    ('lost_reports', "status='OPEN'", 'CLOSED', 'closed_reports'),
)


class ExpiryService:
    def __init__(self, settings, clock):
        self.settings = settings
        self.clock = clock

    def run(self, db, day, *, manual=False):
        now = self.clock()
        row = db.execute('SELECT * FROM daily_expiry_runs WHERE scheduled_date=%s', (day,)).fetchone()
        if row and row['status'] == 'SUCCEEDED':
            return row
        if row:
            if row['attempts'] >= self.settings.max_attempts:
                db.execute("""UPDATE daily_expiry_runs SET status='FAILED',
                    last_error_code='EXPIRY_ATTEMPTS_EXHAUSTED' WHERE scheduled_date=%s""", (day,))
                return None
            if not manual and row['next_attempt_at'] and row['next_attempt_at'] > now:
                return None

        db.execute('''INSERT INTO daily_expiry_runs
            (scheduled_date,run_id,cutoff_at,status,attempts,expired_items,closed_reports)
            VALUES (%s,%s,%s,'RUNNING',1,0,0)
            ON CONFLICT (scheduled_date) DO UPDATE SET status='RUNNING',
            attempts=daily_expiry_runs.attempts+1, next_attempt_at=NULL, last_error_code=NULL''',
            (day, uuid4(), now))
        row = db.execute('SELECT * FROM daily_expiry_runs WHERE scheduled_date=%s', (day,)).fetchone()
        try:
            for table, condition, status, counter in TARGETS:
                while self.batch(db, row, table, condition, status, counter):
                    pass
            db.execute("""UPDATE daily_expiry_runs SET status='SUCCEEDED',completed_at=%s
                WHERE scheduled_date=%s""", (self.clock(), day))
        except Exception:
            delay = self.settings.retry_delays[min(row['attempts'] - 1, len(self.settings.retry_delays) - 1)]
            db.execute("""UPDATE daily_expiry_runs SET status='FAILED',last_error_code='EXPIRY_FAILED',
                next_attempt_at=%s WHERE scheduled_date=%s""", (self.clock() + timedelta(seconds=delay), day))
            logger.error('EXPIRY_FAILED date=%s attempt=%s', day, row['attempts'])
            return None
        return db.execute('SELECT * FROM daily_expiry_runs WHERE scheduled_date=%s', (day,)).fetchone()

    def batch(self, db, run, table, condition, status, counter):
        cutoff = run['cutoff_at']
        # Candidate reads take no row locks; category locks must always come first.
        candidates = db.execute(f'''SELECT id,category_id FROM {table}
            WHERE {condition} AND expires_at <= %s ORDER BY expires_at,id LIMIT %s''',
            (cutoff, self.settings.batch_size)).fetchall()
        if not candidates:
            return False

        with db.transaction():
            db.execute("SELECT set_config('lock_timeout',%s,true)",
                       (f'{self.settings.lock_timeout_seconds}s',))
            keys = sorted({category_lock_key(row['category_id']) for row in candidates})
            for key in keys:
                db.execute('SELECT pg_advisory_xact_lock(%s,%s)', (MATCHING_LOCK_NAMESPACE, key))
            count = 0
            for candidate in candidates:
                current = db.execute(f'SELECT * FROM {table} WHERE id=%s FOR UPDATE',
                                     (candidate['id'],)).fetchone()
                if current is None:
                    continue
                if current['category_id'] != candidate['category_id']:
                    raise RuntimeError('Expiry category changed; retry with current category')
                if current['status'] != ('POSTED' if table == 'found_items' else 'OPEN'):
                    continue
                if current['expires_at'] > cutoff or (table == 'found_items' and current['deleted_at']):
                    continue
                self.close(db, table, current, status, cutoff)
                count += 1
            db.execute(f'UPDATE daily_expiry_runs SET {counter}={counter}+%s WHERE scheduled_date=%s',
                       (count, run['scheduled_date']))
        return True

    def close(self, db, table, row, status, cutoff):
        db.execute(f'''UPDATE {table} SET status=%s,closed_at=%s,purge_after=%s,
            version=version+1,updated_at=%s WHERE id=%s''',
            (status, cutoff, one_year_after(cutoff), cutoff, row['id']))
        if table == 'found_items':
            # Conversation FK cascades delete every message in the same transaction.
            db.execute('DELETE FROM conversations WHERE item_id=%s', (row['id'],))
            action, target = 'ITEM_STATUS_CHANGED', 'FOUND_ITEM'
        else:
            db.execute('DELETE FROM lost_report_private_details WHERE report_id=%s', (row['id'],))
            action, target = 'LOST_REPORT_STATUS_CHANGED', 'LOST_REPORT'
        # Existing status triggers enqueue expiry notifications and cancel report email items.
        # Analysis/matching consumers recheck status under the same category/owner locks.
        db.execute('''INSERT INTO audit_logs
            (id,actor_type,actor_id,action,target_type,target_id,metadata,occurred_at,purge_after)
            VALUES (%s,'SYSTEM',NULL,%s,%s,%s,%s,%s,%s)''',
            (uuid4(), action, target, row['id'],
             Jsonb({'fromStatus': row['status'], 'toStatus': status}), cutoff, one_year_after(cutoff)))
