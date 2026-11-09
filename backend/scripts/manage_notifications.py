"""Inspect failed deliveries or retry a definitely-unsent failed delivery."""

import argparse
import asyncio
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from library.database import session_factory
from model import EmailDelivery, OutboxEvent
from service.notification_worker import EVENT_TYPES
from service.outbox_worker import utcnow


async def run(args):
    async with session_factory()() as db, db.begin():
        if args.command == 'failures':
            rows = (await db.execute(select(
                EmailDelivery.id, EmailDelivery.status, EmailDelivery.last_error_code,
            ).where(EmailDelivery.status.in_(['FAILED', 'UNKNOWN']))
                .order_by(EmailDelivery.created_at).limit(100))).all()
            for row in rows:
                print(row.id, row.status, row.last_error_code or '-')
            events = (await db.execute(select(OutboxEvent.id, OutboxEvent.last_error_code).where(
                OutboxEvent.event_type.in_(EVENT_TYPES), OutboxEvent.failed_at.is_not(None),
            ).limit(100))).all()
            for row in events:
                print(row.id, 'EVENT_FAILED', row.last_error_code or '-')
            return
        if args.command == 'retry-event':
            event = await db.scalar(select(OutboxEvent).where(
                OutboxEvent.id == args.delivery_id, OutboxEvent.event_type.in_(EVENT_TYPES),
                OutboxEvent.failed_at.is_not(None),
            ).with_for_update())
            if event is None:
                raise ValueError('Only failed notification events may be retried')
            event.failed_at = event.last_error_code = None
            event.attempts, event.next_attempt_at = 0, utcnow()
            return
        delivery = await db.scalar(select(EmailDelivery).where(
            EmailDelivery.id == args.delivery_id, EmailDelivery.status == 'FAILED',
        ).with_for_update())
        if delivery is None:
            raise ValueError('Only definitely-unsent FAILED deliveries may be retried')
        delivery.status, delivery.attempts = 'RETRY', 0
        delivery.next_attempt_at = utcnow()
        delivery.last_error_code = None


def main():
    if not Path('/.dockerenv').exists():
        raise SystemExit('Run inside the existing backend container')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('failures')
    for name in ('retry', 'retry-event'):
        command = commands.add_parser(name)
        command.add_argument('delivery_id', type=UUID)
    try:
        asyncio.run(run(parser.parse_args()))
    except Exception:
        raise SystemExit('NOTIFICATION_MAINTENANCE_FAILED') from None


if __name__ == '__main__':
    main()
