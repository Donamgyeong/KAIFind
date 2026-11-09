"""Per-user email quotas, daily digest and lease-fenced mock delivery."""

import asyncio
from contextlib import suppress
from datetime import datetime, timedelta
import logging
import random
from uuid import uuid4
from zoneinfo import ZoneInfo

from sqlalchemy import or_, select, text, update
from sqlalchemy.dialects.postgresql import insert

from library.email_provider import DeliveryError, EmailMessage, MockEmailProvider
from model import (
    Collection, EmailDelivery, EmailDeliveryItem, EmailDeliveryPolicy, FoundItem,
    LostReport, Notification, NotificationKeywordSource, OutboxEvent, User,
)
from service.notification_events import email_allowed
from service.notifications import MESSAGES
from service.outbox_worker import utcnow


KST = ZoneInfo('Asia/Seoul')
POLICY_LOCK = 73011809
logger = logging.getLogger(__name__)


class EmailWorker:
    def __init__(self, factory, settings, *, clock=utcnow, provider=None):
        self.factory, self.settings, self.clock = factory, settings, clock
        self.provider = provider or MockEmailProvider(factory, clock)
        self.stop = asyncio.Event()
        self.task = None

    async def policy(self, db, now):
        day = now.astimezone(KST).date()
        # The same order is used by every scheduling transaction: policy, user, delivery/items.
        await db.execute(text('SELECT pg_advisory_xact_lock(:key)'), {'key': POLICY_LOCK})
        await db.execute(insert(EmailDeliveryPolicy).values(
            delivery_date=day, daily_limit=self.settings.daily_limit,
            digest_time=self.settings.digest_time, created_at=now,
        ).on_conflict_do_nothing(index_elements=['delivery_date']))
        policy = await db.get(EmailDeliveryPolicy, day)
        if (policy.daily_limit, policy.digest_time) != (self.settings.daily_limit, self.settings.digest_time):
            logger.warning('NOTIFICATION_EMAIL_DAILY_POLICY_DIFFERS_FROM_ENVIRONMENT')
        return policy

    async def eligible(self, db, notification, now):
        if notification is None or notification.purge_after <= now:
            return False
        if not await email_allowed(db, notification.recipient_id, notification.type):
            return False
        item = await db.get(FoundItem, notification.item_id) if notification.item_id else None
        if item is None or item.hidden or item.deleted_at is not None:
            return False
        if notification.type == 'MATCH_CANDIDATE':
            report = await db.get(LostReport, notification.report_id) if notification.report_id else None
            return (item.status == 'POSTED' and report is not None and report.status == 'OPEN'
                    and report.expires_at > now and report.owner_id == notification.recipient_id)
        if notification.type == 'ITEM_COLLECTED':
            event = await db.get(OutboxEvent, notification.event_id)
            collection = await db.get(Collection, event.aggregate_id) if event else None
            return (item.status == 'COLLECTED' and item.finder_id == notification.recipient_id
                    and collection is not None and collection.undone_at is None)
        if notification.type == 'ITEM_EXPIRED':
            return item.status == 'EXPIRED' and item.finder_id == notification.recipient_id
        return item.status == 'POSTED' and bool(await db.scalar(select(
            NotificationKeywordSource.subscription_id,
        ).where(NotificationKeywordSource.notification_id == notification.id).limit(1)))

    @staticmethod
    def slot(deliveries, policy, kind):
        used = {d.slot_no for d in deliveries if d.delivery_date == policy.delivery_date}
        candidates = ([policy.daily_limit] if kind == 'DIGEST' else range(1, policy.daily_limit))
        return next((number for number in candidates if number not in used), None)

    async def schedule(self, recipient_id):
        now = self.clock()
        async with self.factory() as db, db.begin():
            policy = await self.policy(db, now)
            user = await db.scalar(select(User).where(User.id == recipient_id).with_for_update())
            if user is None:
                return
            deliveries = list((await db.scalars(select(EmailDelivery).where(
                EmailDelivery.recipient_id == recipient_id,
            ).order_by(EmailDelivery.created_at, EmailDelivery.id).with_for_update())).all())
            day = policy.delivery_date
            cutoff = datetime.combine(day, policy.digest_time, tzinfo=KST)

            # A worker that disappeared during an external call leaves an unknown result.
            for delivery in deliveries:
                if delivery.status == 'SENDING' and (delivery.lease_until is None or delivery.lease_until <= now):
                    delivery.status = 'UNKNOWN'
                    delivery.lease_token = delivery.lease_until = None
                    delivery.next_attempt_at = now

            # Only definitely-unsent deliveries may move dates or be merged into a digest.
            for delivery in deliveries:
                if (delivery.delivery_date == day or delivery.status not in {'PENDING', 'RETRY'}
                        or delivery.next_attempt_at > now):
                    continue
                number = self.slot(deliveries, policy, delivery.kind)
                if number is not None:
                    delivery.delivery_date, delivery.slot_no = day, number
                    if delivery.kind == 'DIGEST':
                        delivery.next_attempt_at = max(delivery.next_attempt_at, cutoff)
                else:
                    items = (await db.scalars(select(EmailDeliveryItem).where(
                        EmailDeliveryItem.delivery_id == delivery.id,
                        EmailDeliveryItem.status == 'QUEUED',
                    ))).all()
                    target = next((d for d in deliveries if d.kind == 'DIGEST'
                                   and d.delivery_date == day and d.status in {'PENDING', 'RETRY'}), None)
                    for entry in items:
                        if target is not None:
                            entry.delivery_id = target.id
                        else:
                            entry.status, entry.delivery_id = 'PENDING', None
                            entry.digest_on = day
                    delivery.status = 'CANCELLED'

            pending = (await db.execute(select(EmailDeliveryItem, Notification).join(
                Notification, Notification.id == EmailDeliveryItem.notification_id,
            ).where(
                Notification.recipient_id == recipient_id, EmailDeliveryItem.status == 'PENDING',
            ).order_by(EmailDeliveryItem.created_at, EmailDeliveryItem.id).with_for_update(
                of=EmailDeliveryItem,
            ))).all()
            digest_items = []
            for entry, notification in pending:
                if not await self.eligible(db, notification, now):
                    entry.status = 'CANCELLED'
                    continue
                if entry.digest_on is None:
                    number = self.slot(deliveries, policy, 'INDIVIDUAL')
                    if number is not None:
                        delivery = EmailDelivery(
                            recipient_id=recipient_id, delivery_date=day, kind='INDIVIDUAL',
                            slot_no=number, status='PENDING', attempts=0,
                            next_attempt_at=now, created_at=now,
                        )
                        db.add(delivery)
                        await db.flush()
                        deliveries.append(delivery)
                        entry.status, entry.delivery_id = 'QUEUED', delivery.id
                        continue
                    entry.digest_on = day if notification.created_at < cutoff else day + timedelta(days=1)
                if entry.digest_on <= day and notification.created_at < cutoff:
                    digest_items.append(entry)

            number = self.slot(deliveries, policy, 'DIGEST')
            # An older UNKNOWN digest must be reconciled before another one is sent.
            unknown_digest = any(d.kind == 'DIGEST' and d.status in {'UNKNOWN', 'SENDING'} for d in deliveries)
            if digest_items and now >= cutoff and number is not None and not unknown_digest:
                delivery = EmailDelivery(
                    recipient_id=recipient_id, delivery_date=day, kind='DIGEST',
                    slot_no=number, status='PENDING', attempts=0, next_attempt_at=now, created_at=now,
                )
                db.add(delivery)
                await db.flush()
                for entry in digest_items:
                    entry.status, entry.delivery_id = 'QUEUED', delivery.id
            elif number is None:
                for entry in digest_items:
                    entry.digest_on = day + timedelta(days=1)

    async def claim(self, recipient_id):
        now = self.clock()
        async with self.factory() as db, db.begin():
            await db.execute(select(User.id).where(User.id == recipient_id).with_for_update())
            delivery = await db.scalar(select(EmailDelivery).where(
                EmailDelivery.recipient_id == recipient_id,
                EmailDelivery.status.in_(['UNKNOWN', 'PENDING', 'RETRY']),
                EmailDelivery.next_attempt_at <= now,
                or_(EmailDelivery.lease_until.is_(None), EmailDelivery.lease_until <= now),
            ).order_by(
                (EmailDelivery.status != 'UNKNOWN'), EmailDelivery.created_at, EmailDelivery.id,
            ).with_for_update(skip_locked=True).limit(1))
            if delivery is None:
                return None
            if delivery.status != 'UNKNOWN' and delivery.delivery_date != now.astimezone(KST).date():
                return None
            delivery.lease_token = uuid4()
            delivery.lease_until = now + timedelta(seconds=self.settings.lease_seconds)
            if delivery.status == 'UNKNOWN':
                return delivery, None

            entries = (await db.execute(select(EmailDeliveryItem, Notification).join(
                Notification, Notification.id == EmailDeliveryItem.notification_id,
            ).where(EmailDeliveryItem.delivery_id == delivery.id, EmailDeliveryItem.status == 'QUEUED')
                .order_by(EmailDeliveryItem.created_at, EmailDeliveryItem.id))).all()
            user = await db.get(User, recipient_id)
            lines = []
            for entry, notification in entries:
                if not await self.eligible(db, notification, now):
                    entry.status = 'CANCELLED'
                    continue
                path = (f'/lost-reports/{notification.report_id}/matches'
                        if notification.type == 'MATCH_CANDIDATE'
                        else f'/found-items/{notification.item_id}')
                lines.append(MESSAGES[notification.type][user.language == 'en'] + '\n'
                             + self.settings.app_base_url + path)
            if not lines:
                delivery.status = 'CANCELLED'
                delivery.lease_token = delivery.lease_until = None
                return None
            delivery.status = 'SENDING'
            delivery.attempts += 1
            subject = ('KAIFind 알림 요약' if delivery.kind == 'DIGEST' else 'KAIFind 알림')
            if user.language == 'en':
                subject = 'KAIFind notification digest' if delivery.kind == 'DIGEST' else 'KAIFind notification'
            return delivery, EmailMessage(delivery.id, user.email, subject, '\n\n'.join(lines))

    async def finish(self, delivery, *, message_id=None, error=None, absent=False):
        now = self.clock()
        async with self.factory() as db, db.begin():
            row = await db.scalar(select(EmailDelivery).where(
                EmailDelivery.id == delivery.id, EmailDelivery.lease_token == delivery.lease_token,
                EmailDelivery.lease_until > now, EmailDelivery.status.in_(['SENDING', 'UNKNOWN']),
            ).with_for_update())
            if row is None:
                return
            row.lease_token = row.lease_until = None
            if message_id is not None:
                row.status, row.provider_message_id, row.sent_at = 'SENT', message_id, now
                row.last_error_code = None
                await db.execute(update(EmailDeliveryItem).where(
                    EmailDeliveryItem.delivery_id == row.id, EmailDeliveryItem.status == 'QUEUED',
                ).values(status='SENT'))
            elif absent:
                row.status = 'FAILED' if row.attempts >= self.settings.max_attempts else 'RETRY'
                row.next_attempt_at = now
            else:
                error = error or DeliveryError('PROVIDER_RESULT_UNKNOWN', unknown=True)
                row.last_error_code = error.code
                if error.unknown:
                    row.status = 'UNKNOWN'
                elif error.permanent or row.attempts >= self.settings.max_attempts:
                    row.status = 'FAILED'
                    logger.error('NOTIFICATION_EMAIL_DELIVERY_FAILED delivery_id=%s', row.id)
                else:
                    row.status = 'RETRY'
                interval = self.settings.retry_seconds[min(max(row.attempts - 1, 0), len(self.settings.retry_seconds) - 1)]
                interval *= random.uniform(1 - self.settings.retry_jitter_ratio, 1 + self.settings.retry_jitter_ratio)
                row.next_attempt_at = now + timedelta(seconds=interval)

    async def process(self, claim):
        delivery, message = claim
        try:
            if message is None:
                message_id = await asyncio.wait_for(
                    self.provider.lookup(delivery.id), self.settings.timeout_seconds,
                )
                await self.finish(delivery, message_id=message_id, absent=message_id is None)
            else:
                # Recheck the date at the external-call boundary; do not send on yesterday's slot.
                if self.clock().astimezone(KST).date() != delivery.delivery_date:
                    await self.finish(delivery, absent=True)
                    return
                message_id = await asyncio.wait_for(self.provider.send(message), self.settings.timeout_seconds)
                await self.finish(delivery, message_id=message_id)
        except DeliveryError as error:
            await self.finish(delivery, error=error)
        except Exception:
            # Includes a provider success followed by failure to save its receipt locally.
            await self.finish(delivery, error=DeliveryError('PROVIDER_RESULT_UNKNOWN', unknown=True))

    async def run_once(self):
        if not self.settings.enabled:
            return False
        async with self.factory() as db:
            pending_users = select(Notification.recipient_id).join(
                EmailDeliveryItem, Notification.id == EmailDeliveryItem.notification_id,
            ).where(EmailDeliveryItem.status == 'PENDING')
            active_users = select(EmailDelivery.recipient_id).where(
                EmailDelivery.status.in_(['PENDING', 'RETRY', 'UNKNOWN', 'SENDING']),
            )
            recipients = (await db.scalars(pending_users.union(active_users))).all()
        did_work = False
        for recipient_id in recipients:
            await self.schedule(recipient_id)
            claim = await self.claim(recipient_id)
            if claim is not None:
                await self.process(claim)
                did_work = True
        return did_work

    async def run(self):
        while not self.stop.is_set():
            try:
                if await self.run_once():
                    continue
            except Exception:
                logger.error('NOTIFICATION_EMAIL_WORKER_CYCLE_FAILED')
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop.wait(), self.settings.poll_seconds)

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.stop.set()
        if self.task:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), self.settings.timeout_seconds + 5)
            except asyncio.TimeoutError:
                self.task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.task
