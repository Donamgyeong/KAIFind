"""Inspect, retry and clean up keyword registration work in the backend container."""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from library.database import session_factory
from model import KeywordRegistrationEvent
from service.keyword_maintenance import cleanup, retry_event


async def run(args):
    async with session_factory()() as db, db.begin():
        if args.command == 'failures':
            rows = (await db.execute(select(
                KeywordRegistrationEvent.id, KeywordRegistrationEvent.status,
                KeywordRegistrationEvent.last_error_code,
            ).where(KeywordRegistrationEvent.last_error_code.is_not(None))
                .order_by(KeywordRegistrationEvent.registered_at).limit(100))).all()
            for row in rows:
                print(row.id, row.status, row.last_error_code)
        elif args.command == 'retry':
            await retry_event(db, args.event_id)
        else:
            print('expired_snapshots', await cleanup(db))


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('Run inside the existing backend container')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('failures')
    commands.add_parser('cleanup')
    retry = commands.add_parser('retry')
    retry.add_argument('event_id', type=UUID)
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception:
        raise SystemExit('KEYWORD_MAINTENANCE_FAILED') from None


if __name__ == '__main__':
    main()
