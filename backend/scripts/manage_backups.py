"""Manual backup and safe execution history inspection."""

import argparse
import json

from library.backup_settings import BackupSettings
from service.database_backup import DatabaseBackupService


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['run', 'status'])
    args = parser.parse_args()
    try:
        service = DatabaseBackupService(BackupSettings())
        if args.command == 'run':
            result = service.run_once(manual=True)
            print(result)
            raise SystemExit(0 if result == 'SUCCEEDED' else 1)
        with service.connect() as db:
            rows = db.execute('SELECT * FROM database_backups ORDER BY scheduled_date DESC LIMIT 30').fetchall()
            expiry = db.execute('SELECT * FROM daily_expiry_runs ORDER BY scheduled_date DESC LIMIT 30').fetchall()
        print(json.dumps({'backups': rows, 'expiry': expiry}, default=str, indent=2))
    except Exception:
        raise SystemExit('BACKUP_COMMAND_FAILED: check configuration and service availability') from None


if __name__ == '__main__':
    main()
