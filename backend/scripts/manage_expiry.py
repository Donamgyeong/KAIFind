"""Run expiry without backup, or inspect daily expiry history."""

import argparse
import json
from zoneinfo import ZoneInfo

from library.backup_settings import BackupSettings
from service.database_backup import DatabaseBackupService, LOCK_KEY


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'status'])
    args = parser.parse_args()
    try:
        service = DatabaseBackupService(BackupSettings())
        with service.connect() as db:
            if args.command == 'status':
                rows = db.execute('SELECT * FROM daily_expiry_runs ORDER BY scheduled_date DESC LIMIT 30').fetchall()
                print(json.dumps(rows, default=str, indent=2))
                return
            if not db.execute('SELECT pg_try_advisory_lock(%s) AS locked', (LOCK_KEY,)).fetchone()['locked']:
                raise SystemExit('BUSY')
            day = service.clock().astimezone(ZoneInfo(service.settings.timezone)).date()
            row = service.expiry.run(db, day, manual=True)
            print('SUCCEEDED' if row else 'EXPIRY_BLOCKED')
            raise SystemExit(0 if row else 1)
    except Exception:
        raise SystemExit('EXPIRY_COMMAND_FAILED: check configuration and service availability') from None


if __name__ == '__main__':
    main()
