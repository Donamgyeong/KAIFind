"""Consume only collection/expiry events; analysis events remain untouched."""

import asyncio
from contextlib import suppress
from datetime import timedelta
import logging

from sqlalchemy import select

from model import Collection, FoundItem, OutboxEvent
from service.notification_events import create_notification
from service.outbox_worker import utcnow


EVENT_TYPES = ('COLLECTION_NOTIFICATION', 'EXPIRY_NOTIFICATION')
logger = logging.getLogger(__name__)


class NotificationWorker:
    def __init__(self, factory, *, clock=utcnow, poll_seconds=5):
        self.factory, self.clock, self.poll_seconds = factory, clock, poll_seconds
        self.stop = asyncio.Event()
        self.task = None

    async def run_once(self):
        async with self.factory() as db, db.begin():
            now = self.clock()
            event = await db.scalar(select(OutboxEvent).where(
                OutboxEvent.event_type.in_(EVENT_TYPES), OutboxEvent.processed_at.is_(None),
                OutboxEvent.failed_at.is_(None), OutboxEvent.cancelled_at.is_(None),
                OutboxEvent.next_attempt_at <= now,
            ).order_by(OutboxEvent.created_at, OutboxEvent.id)
                .with_for_update(skip_locked=True).limit(1))
            if event is None:
                return False

            try:
                async with db.begin_nested():
                    await self.consume(db, event, now)
            except Exception:
                event.attempts += 1
                event.last_error_code = 'NOTIFICATION_EVENT_FAILED'
                event.next_attempt_at = now + timedelta(seconds=min(1800, 60 * 2 ** min(event.attempts - 1, 5)))
                if event.attempts >= 10:
                    event.failed_at = now
                    logger.error('NOTIFICATION_EVENT_FAILED event_id=%s', event.id)
            return True

    async def consume(self, db, event, now):
        # No external calls: event and notifications commit in one short transaction.
        item = await db.get(FoundItem, event.payload['itemId'])
        collection = (await db.get(Collection, event.aggregate_id)
                      if event.event_type == 'COLLECTION_NOTIFICATION' else None)
        valid = item is not None and item.deleted_at is None
        if valid:
            if event.event_type == 'COLLECTION_NOTIFICATION':
                valid = collection is not None and collection.undone_at is None and item.status == 'COLLECTED'
            else:
                valid = item.status == 'EXPIRED'
        if not valid:
            event.cancelled_at = now
            return

        await create_notification(
            db, event_id=event.id, recipient_id=item.finder_id,
            kind='ITEM_COLLECTED' if collection else 'ITEM_EXPIRED',
            item_id=item.id, now=event.created_at,
        )
        event.processed_at = now

    async def run(self):
        while not self.stop.is_set():
            try:
                if await self.run_once():
                    continue
            except Exception:
                logger.error('NOTIFICATION_WORKER_CYCLE_FAILED')
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop.wait(), self.poll_seconds)

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.stop.set()
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 10)
            except asyncio.TimeoutError:
                self.task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.task
