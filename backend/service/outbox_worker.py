"""Lease-fenced text-analysis consumer; inference never holds a DB transaction."""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timedelta, timezone
import logging
import random
from uuid import uuid4

from sqlalchemy import or_, select, update

from library.matching_lock import lock_matching_categories
from library.text_analysis_types import AnalysisError
from model import OutboxEvent
from service.text_analysis import KINDS, analysis_input, eligible, enqueue_reevaluation
from service.text_analysis_profiles import active_policy


logger = logging.getLogger(__name__)


def utcnow():
    return datetime.now(timezone.utc)


def pending():
    return (
        OutboxEvent.processed_at.is_(None), OutboxEvent.failed_at.is_(None),
        OutboxEvent.cancelled_at.is_(None),
    )


class AnalysisWorker:
    def __init__(self, runtime, factory, *, clock=utcnow, lease_seconds=60,
                 max_attempts=5, poll_seconds=1):
        if lease_seconds <= 0 or max_attempts < 1 or poll_seconds <= 0:
            raise ValueError('Invalid analysis worker limits')
        self.runtime = runtime
        self.factory = factory
        self.clock = clock
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.poll_seconds = poll_seconds
        self.stop = asyncio.Event()
        self.task = None

    async def claim(self):
        async with self.factory() as db, db.begin():
            now = self.clock()
            event = (await db.execute(select(OutboxEvent).where(
                *pending(), OutboxEvent.event_type.in_(KINDS),
                OutboxEvent.next_attempt_at <= now,
                or_(OutboxEvent.lease_until.is_(None), OutboxEvent.lease_until <= now),
            ).order_by(OutboxEvent.next_attempt_at, OutboxEvent.id)
                .with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
            if event is None:
                return None
            event.attempts += 1
            event.lease_token = uuid4()
            event.lease_until = now + timedelta(seconds=self.lease_seconds)
            return event

    def fence(self, event):
        return (
            OutboxEvent.id == event.id, OutboxEvent.lease_token == event.lease_token,
            OutboxEvent.lease_until > self.clock(), *pending(),
        )

    async def heartbeat(self, event):
        while True:
            await asyncio.sleep(self.lease_seconds / 3)
            async with self.factory() as db, db.begin():
                changed = await db.execute(update(OutboxEvent).where(*self.fence(event)).values(
                    lease_until=self.clock() + timedelta(seconds=self.lease_seconds),
                ))
                if changed.rowcount != 1:
                    return

    @asynccontextmanager
    async def locked_work(self, event):
        owner_model, feature_model, owner_column, _ = KINDS[event.event_type]
        async with self.factory() as db, db.begin():
            # Locate without row locks, then acquire the category before the owner.
            owner_id = (await db.execute(select(getattr(feature_model, owner_column)).where(
                feature_model.id == event.aggregate_id,
            ))).scalar_one_or_none()
            category = (await db.execute(select(owner_model.category_id).where(
                owner_model.id == owner_id,
            ))).scalar_one_or_none()
            if category is not None:
                await lock_matching_categories(db, [category])
            owner = (await db.execute(select(owner_model).where(owner_model.id == owner_id)
                .with_for_update())).scalar_one_or_none()
            if owner is not None and owner.category_id != category:
                raise AnalysisError('CONCURRENT_MODIFICATION', retryable=True)
            feature = (await db.execute(select(feature_model).where(
                feature_model.id == event.aggregate_id,
            ).with_for_update())).scalar_one_or_none()
            current = (await db.execute(select(OutboxEvent).where(*self.fence(event))
                .with_for_update())).scalar_one_or_none()
            deadline = current.lease_until if current is not None else None
            yield db, owner, feature, current
            if deadline is not None and self.clock() >= deadline:
                await db.rollback()

    def terminal(self, event, field, now, code=None):
        setattr(event, field, now)
        event.lease_token = None
        event.lease_until = None
        event.last_error_code = code

    async def check_current(self, db, owner, feature, event):
        if event is None:
            return False
        now = self.clock()
        policy, profile = await active_policy(db, self.runtime.profile)
        if (owner is None or feature is None or not eligible(owner, now)
                or feature.profile_id != profile.id or feature.text_version != owner.text_version):
            if feature is not None and feature.status != 'READY':
                feature.status = 'SUPERSEDED'
                feature.completed_at = now
                feature.last_error_code = None
                feature.updated_at = now
            self.terminal(event, 'cancelled_at', now)
            return False
        if feature.status == 'READY':
            self.terminal(event, 'processed_at', now)
            return False
        if feature.source_hash != analysis_input(owner).source_hash:
            raise AnalysisError('SOURCE_HASH_MISMATCH')
        return policy

    async def process(self, event):
        pulse = asyncio.create_task(self.heartbeat(event))
        try:
            async with self.locked_work(event) as (db, owner, feature, current):
                if not await self.check_current(db, owner, feature, current):
                    return
                if event.attempts > self.max_attempts:
                    raise AnalysisError('ANALYSIS_RETRY_EXHAUSTED')
                value = analysis_input(owner)
                feature.status = 'PROCESSING'
                feature.updated_at = self.clock()
            result = await self.runtime.analyze(value)
            async with self.locked_work(event) as (db, owner, feature, current):
                policy = await self.check_current(db, owner, feature, current)
                if not policy:
                    return
                if (result.source_hash != feature.source_hash
                        or result.profile_fingerprint != self.runtime.profile['fingerprint']):
                    raise AnalysisError('ANALYSIS_RESULT_MISMATCH')
                now = self.clock()
                feature.status = 'READY'
                feature.translated_text = result.translated_text
                feature.keywords = list(result.keywords)
                feature.attributes = result.attributes
                feature.completed_at = now
                feature.updated_at = now
                feature.last_error_code = None
                await enqueue_reevaluation(db, owner=owner, policy_id=policy.id, now=now)
                # A heartbeat cannot revive an expired token. Recheck time at write.
                changed = await db.execute(update(OutboxEvent).where(*self.fence(event)).values(
                    processed_at=now, lease_token=None, lease_until=None, last_error_code=None,
                ))
                if changed.rowcount != 1:
                    await db.rollback()
        except AnalysisError as error:
            await self.failure(event, error)
        except Exception:
            # Unexpected inference/validation errors are safe codes only.
            await self.failure(event, AnalysisError('ANALYSIS_FAILED', retryable=True))
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError):
                await pulse

    async def failure(self, event, error):
        async with self.locked_work(event) as (db, owner, feature, current):
            if current is None:
                return
            now = self.clock()
            if feature is None or owner is None or not eligible(owner, now) or feature.text_version != owner.text_version:
                if feature is not None and feature.status != 'READY':
                    feature.status = 'SUPERSEDED'
                    feature.completed_at = now
                    feature.last_error_code = None
                self.terminal(current, 'cancelled_at', now)
                return
            if error.retryable and event.attempts < self.max_attempts:
                feature.status = 'PENDING'
                feature.updated_at = now
                current.lease_token = None
                current.lease_until = None
                current.last_error_code = error.code
                current.next_attempt_at = now + timedelta(
                    seconds=random.uniform(0.5, 1) * min(300, 2 ** min(event.attempts, 9)),
                )
            else:
                feature.status = 'FAILED'
                feature.completed_at = now
                feature.updated_at = now
                feature.last_error_code = error.code
                self.terminal(current, 'failed_at', now, error.code)

    async def run_once(self):
        # Timeout/cancellation leaves the inference thread running. Do not claim
        # more durable work until that actual future has drained.
        future = getattr(self.runtime, '_future', None)
        if future is not None and not future.done():
            return False
        event = await self.claim()
        if event is None:
            return False
        await self.process(event)
        return True

    async def run(self):
        while not self.stop.is_set():
            try:
                if await self.run_once():
                    continue
            except Exception:
                # No raw DB/library exception: query parameters can contain text.
                logger.error('TEXT_ANALYSIS_WORKER_CYCLE_FAILED')
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop.wait(), self.poll_seconds)

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.stop.set()
        if self.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 10)
            except asyncio.TimeoutError:
                self.task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.task
