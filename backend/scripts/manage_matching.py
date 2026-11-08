"""Repair missing evaluation jobs or retry one failed job with an audit event."""
import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from library.database import session_factory
from model import FoundItem, LostReport
from service.matching_maintenance import repair_batch, retry_failed
from service.outbox_worker import utcnow


async def run(args):
    factory = session_factory()
    if args.command == 'retry':
        async with factory() as db, db.begin():
            await retry_failed(db, job_id=args.job_id, now=utcnow())
        return
    for model in (FoundItem, LostReport):
        after = None
        while True:
            async with factory() as db, db.begin():
                after = await repair_batch(db, model=model, now=utcnow(), after=after)
            if after is None:
                break


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('Run inside the existing backend container')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('repair')
    retry = commands.add_parser('retry')
    retry.add_argument('job_id', type=UUID)
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception:
        raise SystemExit('MATCHING_MAINTENANCE_FAILED') from None


if __name__ == '__main__':
    main()
