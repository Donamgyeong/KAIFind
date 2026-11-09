"""Lease-fenced registration analysis and per-recipient atomic notifications."""

import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
from uuid import uuid4

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert

from library.keyword_subscription_matching import SUBSCRIPTION_RULE, all_terms_match, atomic_terms
from library.text_analysis_types import AnalysisError, AnalysisInput
from model import (
    FoundItem, KeywordRegistrationEvent, KeywordSubscription, KeywordSubscriptionFeature,
    MatchingRuntime, TextAnalysisProfile, User,
)
from service.notification_events import create_notification
from service.outbox_worker import utcnow
from service.text_analysis_profiles import active_policy


logger = logging.getLogger(__name__)
LEASE_SECONDS = 120


class KeywordWorker:
    def __init__(self, runtime, factory, *, clock=utcnow, poll_seconds=5):
        self.runtime, self.factory, self.clock = runtime, factory, clock
        self.poll_seconds = poll_seconds
        self.stop = asyncio.Event()
        self.task = None

    def fence(self, event):
        return (
            KeywordRegistrationEvent.id == event.id,
            KeywordRegistrationEvent.lease_token == event.lease_token,
            KeywordRegistrationEvent.lease_until > self.clock(),
            KeywordRegistrationEvent.status.in_(('PENDING', 'READY')),
        )

    async def claim(self):
        async with self.factory() as db, db.begin():
            now = self.clock()
            event = await db.scalar(select(KeywordRegistrationEvent).where(
                KeywordRegistrationEvent.status.in_(('PENDING', 'READY')),
                KeywordRegistrationEvent.next_attempt_at <= now,
                (KeywordRegistrationEvent.lease_until.is_(None)) | (KeywordRegistrationEvent.lease_until <= now),
            ).order_by(KeywordRegistrationEvent.next_attempt_at, KeywordRegistrationEvent.id)
                .with_for_update(skip_locked=True).limit(1))
            if event is None:
                return None
            event.lease_token = uuid4()
            event.lease_until = now + timedelta(seconds=LEASE_SECONDS)
            return event

    async def heartbeat(self, event):
        while True:
            await asyncio.sleep(LEASE_SECONDS / 3)
            async with self.factory() as db, db.begin():
                result = await db.execute(update(KeywordRegistrationEvent).where(*self.fence(event)).values(
                    lease_until=self.clock() + timedelta(seconds=LEASE_SECONDS),
                ))
                if not result.rowcount:
                    return

    async def analyze(self, value, expected_fingerprint):
        if self.runtime.profile['fingerprint'] != expected_fingerprint:
            raise AnalysisError('ANALYSIS_PROFILE_MISMATCH')
        result = await self.runtime.analyze(value)
        if result.source_hash != value.source_hash or result.profile_fingerprint != expected_fingerprint:
            raise AnalysisError('KEYWORD_ANALYSIS_MISMATCH')
        return result

    async def prepare(self, event):
        async with self.factory() as db, db.begin():
            # Binding an initially unconfigured event must serialize with activation.
            await db.scalar(select(MatchingRuntime).where(MatchingRuntime.id == 1).with_for_update())
            current = await db.scalar(select(KeywordRegistrationEvent).where(*self.fence(event)).with_for_update())
            if current is None:
                return False
            if current.profile_id is None:
                _, profile = await active_policy(db, self.runtime.profile)
                current.profile_id = profile.id
            profile = await db.get(TextAnalysisProfile, current.profile_id)
            fingerprint = profile.fingerprint
            value = (AnalysisInput(title=current.source_title, description=current.source_description)
                     if current.status == 'PENDING' else None)
            if current.rule_version != SUBSCRIPTION_RULE:
                raise AnalysisError('KEYWORD_RULE_MISMATCH')
            event.profile_id = current.profile_id
        if value is None:
            return True

        result = await self.analyze(value, fingerprint)
        async with self.factory() as db, db.begin():
            current = await db.scalar(select(KeywordRegistrationEvent).where(*self.fence(event)).with_for_update())
            if current is None:
                return False
            current.terms = list(atomic_terms(result.keywords))
            current.source_hash = result.source_hash
            current.source_title = current.source_description = None
            current.status = 'READY'
        return True

    async def ensure_feature(self, event, subscription):
        async with self.factory() as db:
            feature = await db.scalar(select(KeywordSubscriptionFeature).where(
                KeywordSubscriptionFeature.subscription_id == subscription.id,
                KeywordSubscriptionFeature.profile_id == event.profile_id,
                KeywordSubscriptionFeature.rule_version == SUBSCRIPTION_RULE,
            ))
            if feature is not None:
                if feature.status == 'FAILED':
                    raise AnalysisError(feature.last_error_code)
                return
            profile = await db.get(TextAnalysisProfile, event.profile_id)
            fingerprint = profile.fingerprint
        value = AnalysisInput(description=subscription.keyword)
        result = await self.analyze(value, fingerprint)
        terms = atomic_terms(result.keywords)
        async with self.factory() as db, db.begin():
            # User/subscription locking matches DELETE. Inference never holds these locks.
            await db.scalar(select(User.id).where(User.id == subscription.user_id).with_for_update())
            live = await db.scalar(select(KeywordSubscription.id).where(
                KeywordSubscription.id == subscription.id,
            ).with_for_update())
            if live is None:
                return
            await db.execute(insert(KeywordSubscriptionFeature).values(
                subscription_id=subscription.id, profile_id=event.profile_id,
                rule_version=SUBSCRIPTION_RULE, status='READY' if terms else 'FAILED',
                terms=list(terms) if terms else None, source_hash=result.source_hash,
                completed_at=self.clock(), last_error_code=None if terms else 'NO_MATCHABLE_TERMS',
            ).on_conflict_do_nothing(index_elements=['subscription_id', 'profile_id', 'rule_version']))
        if not terms:
            raise AnalysisError('NO_MATCHABLE_TERMS')

    async def recipient(self, event):
        async with self.factory() as db:
            current = await db.scalar(select(KeywordRegistrationEvent).where(*self.fence(event)))
            if current is None:
                return False
            query = select(KeywordSubscription.user_id).where(
                KeywordSubscription.registration_order < current.registration_order,
            )
            if current.cursor_user_id is not None:
                query = query.where(KeywordSubscription.user_id > current.cursor_user_id)
            recipient_id = await db.scalar(query.order_by(KeywordSubscription.user_id).limit(1))
            subscriptions = list((await db.scalars(select(KeywordSubscription).where(
                KeywordSubscription.user_id == recipient_id,
                KeywordSubscription.registration_order < current.registration_order,
            ))).all()) if recipient_id else []
        for subscription in subscriptions:
            await self.ensure_feature(event, subscription)

        async with self.factory() as db, db.begin():
            # Domain state changes acquire the item before the registration event trigger.
            item = await db.scalar(select(FoundItem).where(FoundItem.id == event.item_id).with_for_update())
            if recipient_id:
                await db.scalar(select(User.id).where(User.id == recipient_id).with_for_update())
            subscriptions = list((await db.scalars(select(KeywordSubscription).where(
                KeywordSubscription.user_id == recipient_id,
                KeywordSubscription.registration_order < event.registration_order,
            ).order_by(KeywordSubscription.id).with_for_update())).all()) if recipient_id else []
            current = await db.scalar(select(KeywordRegistrationEvent).where(*self.fence(event)).with_for_update())
            if current is None:
                return False
            deadline = current.lease_until
            if item is None or item.hidden or item.deleted_at is not None or item.status != 'POSTED':
                current.status = 'CANCELLED'
            elif recipient_id is None:
                current.status = 'DONE'
            else:
                features = list((await db.scalars(select(KeywordSubscriptionFeature).where(
                    KeywordSubscriptionFeature.subscription_id.in_([row.id for row in subscriptions]),
                    KeywordSubscriptionFeature.profile_id == event.profile_id,
                    KeywordSubscriptionFeature.rule_version == SUBSCRIPTION_RULE,
                ))).all())
                by_id = {row.subscription_id: row for row in features}
                matched = []
                for subscription in subscriptions:
                    feature = by_id.get(subscription.id)
                    if feature is None or feature.status != 'READY':
                        raise AnalysisError('KEYWORD_FEATURE_NOT_READY', retryable=True)
                    if all_terms_match(feature.terms, current.terms):
                        matched.append(subscription.id)
                if matched:
                    await create_notification(
                        db, event_id=current.id, recipient_id=recipient_id, kind='KEYWORD_MATCH',
                        item_id=item.id, now=current.registered_at, subscription_ids=matched,
                    )
                current.cursor_user_id = recipient_id
                current.attempts = 0
                current.last_error_code = None
            if current.status in {'DONE', 'CANCELLED'}:
                current.completed_at = self.clock()
                current.lease_token = current.lease_until = None
            # Fence even an unusually long DB transaction before committing progress.
            if deadline <= self.clock():
                await db.rollback()
                return False
            return current.status == 'READY'

    async def fail(self, event, code):
        async with self.factory() as db, db.begin():
            current = await db.scalar(select(KeywordRegistrationEvent).where(*self.fence(event)).with_for_update())
            if current is None:
                return
            waiting = code in {'ANALYSIS_BUSY', 'MODEL_NOT_READY', 'KEYWORD_FEATURE_NOT_READY'}
            if not waiting:
                current.attempts += 1
            current.last_error_code = code
            current.next_attempt_at = self.clock() + timedelta(
                seconds=5 if waiting else min(1800, 60 * 2 ** min(current.attempts - 1, 5)),
            )
            current.lease_token = current.lease_until = None
            if current.attempts >= 10:
                current.status, current.failed_at = 'FAILED', self.clock()
                logger.error('KEYWORD_EVENT_FAILED event_id=%s code=%s', current.id, code)

    async def run_once(self):
        event = await self.claim()
        if event is None:
            return False
        pulse = asyncio.create_task(self.heartbeat(event))
        try:
            if await self.prepare(event):
                while await self.recipient(event):
                    pass
        except AnalysisError as exc:
            await self.fail(event, exc.code)
        except Exception:
            logger.error('KEYWORD_EVENT_FAILED event_id=%s', event.id)
            await self.fail(event, 'KEYWORD_EVENT_FAILED')
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError):
                await pulse
        return True

    async def run(self):
        while not self.stop.is_set():
            try:
                if await self.run_once():
                    continue
            except Exception:
                logger.error('KEYWORD_WORKER_CYCLE_FAILED')
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
