"""Real PostgreSQL quota, digest, lease and provider recovery integration."""

import asyncio
from dataclasses import replace
from datetime import datetime, time, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update

from library.email_provider import DeliveryError, MockEmailProvider
from library.notification_settings import NotificationSettings
from model import (
    Collection, EmailDelivery, EmailDeliveryItem, EmailDeliveryPolicy, FoundItem,
    MockEmailReceipt, Notification, NotificationSetting, OutboxEvent,
)
from service.email_worker import EmailWorker, KST
from service.notification_events import create_notification
from service.notification_worker import NotificationWorker
from test_schema import seed as seed_fixture
from test_analysis_worker import analysis_env


@pytest.fixture
def mail_env(auth_runtime):
    rt = auth_runtime
    with rt.sync_engine.begin() as db:
        db.execute(text('TRUNCATE categories, buildings, email_delivery_policies, mock_email_receipts, outbox_events CASCADE'))
        ids = seed_fixture.__wrapped__(db)
        db.execute(update(FoundItem).where(FoundItem.id == ids['item']).values(
            status='EXPIRED', closed_at=rt.clock(), expires_at=rt.clock(),
        ))
        # Explicit producer tests handle the trigger event separately.
        db.execute(text('TRUNCATE outbox_events'))
    settings = NotificationSettings(enabled=True, app_base_url='https://kaifind.example',
                                    daily_limit=3, retry_jitter_ratio=0)
    yield SimpleNamespace(rt=rt, ids=ids, factory=rt.factory, clock=rt.clock, settings=settings)
    with rt.sync_engine.begin() as db:
        db.execute(text('TRUNCATE categories, buildings, email_delivery_policies, mock_email_receipts, outbox_events CASCADE'))


async def add(env, count=1):
    ids = []
    async with env.factory() as db, db.begin():
        for _ in range(count):
            ids.append(await create_notification(
                db, event_id=uuid4(), recipient_id=env.ids['finder'], kind='ITEM_EXPIRED',
                item_id=env.ids['item'], now=env.clock(),
            ))
    return ids


def worker(env, **kwargs):
    return EmailWorker(env.factory, env.settings, clock=env.clock, **kwargs)


async def rows(env, model):
    async with env.factory() as db:
        return list((await db.scalars(select(model))).all())


async def drain(w):
    for _ in range(30):
        if not await w.run_once():
            return
    pytest.fail('Email worker did not become idle')


def at(env, hour, minute=0):
    local = env.clock().astimezone(KST)
    env.clock.now = local.replace(hour=hour, minute=minute, second=0, microsecond=0).astimezone(timezone.utc)


@pytest.mark.asyncio
async def test_individual_then_digest_and_after_cutoff(mail_env):
    env = mail_env
    await add(env, 5)
    w = worker(env)
    await drain(w)
    assert len(await rows(env, MockEmailReceipt)) == 2
    entries = await rows(env, EmailDeliveryItem)
    assert sum(e.status == 'PENDING' for e in entries) == 3
    at(env, 20)
    await drain(w)
    deliveries = await rows(env, EmailDelivery)
    assert len(deliveries) == 3
    assert all(d.status == 'SENT' for d in deliveries)
    digest = next(d for d in deliveries if d.kind == 'DIGEST')
    assert sum(e.delivery_id == digest.id for e in await rows(env, EmailDeliveryItem)) == 3

    await add(env)
    await drain(w)
    pending = [e for e in await rows(env, EmailDeliveryItem) if e.status == 'PENDING']
    assert len(pending) == 1
    assert pending[0].digest_on == env.clock().astimezone(KST).date() + timedelta(days=1)
    env.clock.advance(days=1)
    await drain(w)
    assert len(await rows(env, MockEmailReceipt)) == 4


@pytest.mark.asyncio
async def test_limit_one_digest_only_and_exact_cutoff(mail_env):
    env = mail_env
    env.settings = replace(env.settings, daily_limit=1)
    await add(env)
    at(env, 20)
    await add(env)  # Exactly the cutoff belongs to tomorrow's digest.
    await drain(worker(env))
    assert len(await rows(env, MockEmailReceipt)) == 1
    assert [d.kind for d in await rows(env, EmailDelivery)] == ['DIGEST']
    assert sum(e.status == 'PENDING' for e in await rows(env, EmailDeliveryItem)) == 1


@pytest.mark.asyncio
async def test_settings_change_only_next_day(mail_env):
    env = mail_env
    await add(env, 3)
    await drain(worker(env))
    env.settings = replace(env.settings, daily_limit=5, digest_time=time(21))
    await add(env)
    await drain(worker(env))
    assert len(await rows(env, MockEmailReceipt)) == 2
    policy = (await rows(env, EmailDeliveryPolicy))[0]
    assert policy.daily_limit == 3 and policy.digest_time == time(20)
    env.clock.advance(days=1)
    await add(env, 4)
    await drain(worker(env))
    policies = sorted(await rows(env, EmailDeliveryPolicy), key=lambda p: p.delivery_date)
    assert policies[-1].daily_limit == 5 and policies[-1].digest_time == time(21)


@pytest.mark.asyncio
async def test_concurrent_workers_and_digest_uniqueness(mail_env):
    env = mail_env
    await add(env, 8)
    workers = [worker(env), worker(env)]
    await asyncio.gather(*(drain(w) for w in workers))
    assert len(await rows(env, MockEmailReceipt)) == 2
    at(env, 20)
    await asyncio.gather(*(drain(w) for w in workers))
    deliveries = await rows(env, EmailDelivery)
    assert len(deliveries) == 3
    assert len([d for d in deliveries if d.kind == 'DIGEST']) == 1
    assert len(await rows(env, MockEmailReceipt)) == 3


@pytest.mark.asyncio
async def test_disabled_pauses_queue_and_opt_out_cancels(mail_env):
    env = mail_env
    await add(env)
    disabled = EmailWorker(env.factory, replace(env.settings, enabled=False), clock=env.clock)
    assert not await disabled.run_once()
    assert not await rows(env, EmailDelivery)
    async with env.factory() as db, db.begin():
        db.add(NotificationSetting(user_id=env.ids['finder'], email_enabled=False))
    await drain(worker(env))
    assert (await rows(env, EmailDeliveryItem))[0].status == 'CANCELLED'
    assert len(await rows(env, Notification)) == 1
    assert not await rows(env, MockEmailReceipt)
    await add(env)
    assert len(await rows(env, Notification)) == 2
    assert len(await rows(env, EmailDeliveryItem)) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('change', ['hidden', 'deleted', 'expired_retention'])
async def test_invalid_targets_cancel_before_send(mail_env, change):
    env = mail_env
    ids = await add(env)
    async with env.factory() as db, db.begin():
        if change == 'expired_retention':
            await db.execute(update(Notification).where(Notification.id == ids[0]).values(purge_after=env.clock()))
        else:
            await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
                **({'hidden': True} if change == 'hidden' else {'deleted_at': env.clock()}),
            ))
    await drain(worker(env))
    assert not await rows(env, MockEmailReceipt)


class FaultyProvider(MockEmailProvider):
    calls = 0
    error = None

    async def send(self, message):
        self.calls += 1
        if self.error:
            raise self.error
        return await super().send(message)


@pytest.mark.asyncio
async def test_retry_and_final_failure(mail_env):
    env = mail_env
    env.settings = replace(env.settings, max_attempts=2)
    await add(env)
    provider = FaultyProvider(env.factory, env.clock)
    provider.error = DeliveryError('MOCK_TEMPORARY')
    w = worker(env, provider=provider)
    await w.run_once()
    delivery = (await rows(env, EmailDelivery))[0]
    assert delivery.status == 'RETRY' and delivery.attempts == 1
    assert not await w.run_once()
    env.clock.advance(seconds=60)
    await w.run_once()
    assert (await rows(env, EmailDelivery))[0].status == 'FAILED'
    assert not await rows(env, MockEmailReceipt)


@pytest.mark.asyncio
async def test_provider_success_then_receipt_save_crash_recovers_without_resend(mail_env):
    env = mail_env
    await add(env)
    w = worker(env)
    await w.schedule(env.ids['finder'])
    delivery, message = await w.claim(env.ids['finder'])
    await w.provider.send(message)
    # Simulate a process crash before finish commits.
    env.clock.advance(seconds=121)
    recovered = worker(env)
    await drain(recovered)
    assert (await rows(env, EmailDelivery))[0].status == 'SENT'
    assert len(await rows(env, MockEmailReceipt)) == 1
    # The old lease cannot overwrite recovered completion.
    await w.finish(delivery, error=DeliveryError('STALE_FAILURE'))
    assert (await rows(env, EmailDelivery))[0].status == 'SENT'


@pytest.mark.asyncio
async def test_unknown_absent_retries_and_next_day_reserves_new_slot(mail_env):
    env = mail_env
    await add(env)
    w = worker(env)
    await w.schedule(env.ids['finder'])
    await w.claim(env.ids['finder'])  # Dies before calling the provider.
    env.clock.advance(days=1)
    await drain(worker(env))
    delivery = (await rows(env, EmailDelivery))[0]
    assert delivery.status == 'SENT'
    assert delivery.delivery_date == env.clock().astimezone(KST).date()
    assert len(await rows(env, MockEmailReceipt)) == 1


@pytest.mark.asyncio
async def test_domain_triggers_rollback_and_consumer_isolation(mail_env):
    env = mail_env
    async with env.factory() as db:
        transaction = await db.begin()
        db.add(Collection(item_id=env.ids['item'], finder_id=env.ids['finder'],
                          collector_id=env.ids['member'], purge_after=env.clock() + timedelta(days=365)))
        await db.flush()
        await transaction.rollback()
    assert not await rows(env, OutboxEvent)
    async with env.factory() as db, db.begin():
        await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
            status='POSTED', closed_at=None,
        ))
        await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
            status='EXPIRED', closed_at=env.clock(),
        ))
        db.add(OutboxEvent(event_type='OTHER_CONSUMER', aggregate_id=uuid4(), aggregate_version=1,
                           payload={}, next_attempt_at=env.clock()))
        # Trigger time uses DB clock, but the test worker has an injected clock.
        await db.execute(update(OutboxEvent).values(next_attempt_at=env.clock()))
    consumer = NotificationWorker(env.factory, clock=env.clock)
    assert await consumer.run_once()
    assert not await consumer.run_once()
    assert len(await rows(env, Notification)) == 1
    events = await rows(env, OutboxEvent)
    assert next(e for e in events if e.event_type == 'OTHER_CONSUMER').processed_at is None


@pytest.mark.asyncio
@pytest.mark.parametrize('limit', [2, 20, 50])
async def test_variable_quota_without_empty_digest(mail_env, limit):
    env = mail_env
    env.settings = replace(env.settings, daily_limit=limit)
    await add(env, 2)
    await drain(worker(env))
    assert len(await rows(env, MockEmailReceipt)) == min(2, limit - 1)
    at(env, 20)
    await drain(worker(env))
    assert len(await rows(env, MockEmailReceipt)) == 2
    assert len([d for d in await rows(env, EmailDelivery) if d.kind == 'DIGEST']) == (1 if limit == 2 else 0)


@pytest.mark.asyncio
async def test_mock_body_is_safe_and_uses_profile_language(mail_env):
    env = mail_env
    from model import User
    async with env.factory() as db, db.begin():
        await db.execute(update(User).where(User.id == env.ids['finder']).values(language='en'))
        await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
            title='PRIVATE TITLE', description='PRIVATE DESCRIPTION',
        ))
    await add(env)
    w = worker(env)
    await w.schedule(env.ids['finder'])
    delivery, message = await w.claim(env.ids['finder'])
    assert message.subject == 'KAIFind notification'
    assert message.text == ('Your found item has expired.\nhttps://kaifind.example/found-items/'
                            + str(env.ids['item']))
    assert 'PRIVATE' not in message.text
    await w.process((delivery, message))


@pytest.mark.asyncio
async def test_midnight_recheck_never_sends_on_old_slot(mail_env):
    env = mail_env
    at(env, 23, 59)
    await add(env)
    w = worker(env)
    await w.schedule(env.ids['finder'])
    claim = await w.claim(env.ids['finder'])
    old_day = claim[0].delivery_date
    env.clock.advance(minutes=1)
    await w.process(claim)
    assert not await rows(env, MockEmailReceipt)
    await drain(worker(env))
    delivery = (await rows(env, EmailDelivery))[0]
    assert delivery.delivery_date != old_day and delivery.status == 'SENT'


@pytest.mark.asyncio
async def test_retry_succeeds_and_preserves_logical_id(mail_env):
    env = mail_env
    await add(env)
    provider = FaultyProvider(env.factory, env.clock)
    provider.error = DeliveryError('MOCK_TEMPORARY')
    w = worker(env, provider=provider)
    await w.run_once()
    before = (await rows(env, EmailDelivery))[0]
    provider.error = None
    env.clock.advance(seconds=60)
    await drain(w)
    after = (await rows(env, EmailDelivery))[0]
    assert after.id == before.id and after.slot_no == before.slot_no
    assert after.status == 'SENT' and after.attempts == 2


@pytest.mark.asyncio
async def test_malformed_event_backs_off_then_fails(mail_env):
    env = mail_env
    async with env.factory() as db, db.begin():
        db.add(OutboxEvent(event_type='EXPIRY_NOTIFICATION', aggregate_id=uuid4(),
                           aggregate_version=1, payload={}, next_attempt_at=env.clock()))
    consumer = NotificationWorker(env.factory, clock=env.clock)
    assert await consumer.run_once()
    assert not await consumer.run_once()
    for _ in range(9):
        env.clock.advance(seconds=1800)
        assert await consumer.run_once()
    event = (await rows(env, OutboxEvent))[0]
    assert event.failed_at is not None and event.attempts == 10
    assert not await consumer.run_once()


@pytest.mark.asyncio
async def test_collection_trigger_and_cancelled_collection_email(mail_env):
    env = mail_env
    async with env.factory() as db, db.begin():
        await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(status='COLLECTED'))
        collection = Collection(item_id=env.ids['item'], finder_id=env.ids['finder'],
                                collector_id=env.ids['member'], collected_at=env.clock(),
                                purge_after=env.clock() + timedelta(days=365))
        db.add(collection)
        await db.flush()
        await db.execute(update(OutboxEvent).values(next_attempt_at=env.clock()))
        collection_id = collection.id
    consumer = NotificationWorker(env.factory, clock=env.clock)
    assert await consumer.run_once()
    assert (await rows(env, Notification))[0].type == 'ITEM_COLLECTED'
    async with env.factory() as db, db.begin():
        await db.execute(update(Collection).where(Collection.id == collection_id).values(
            undone_at=env.clock(), undone_by_user_id=env.ids['finder'],
        ))
        await db.execute(update(FoundItem).where(FoundItem.id == env.ids['item']).values(
            status='POSTED', closed_at=None,
        ))
    await drain(worker(env))
    assert not await rows(env, MockEmailReceipt)
    assert (await rows(env, EmailDeliveryItem))[0].status == 'CANCELLED'


@pytest.mark.asyncio
async def test_delayed_digest_retry_waits_for_new_day_cutoff(mail_env):
    env = mail_env
    env.settings = replace(env.settings, daily_limit=1)
    await add(env)
    at(env, 20)
    provider = FaultyProvider(env.factory, env.clock)
    provider.error = DeliveryError('TEMPORARY')
    w = worker(env, provider=provider)
    await w.run_once()
    assert (await rows(env, EmailDelivery))[0].status == 'RETRY'
    env.clock.advance(hours=14)  # 10:00 on the next day.
    provider.error = None
    assert not await w.run_once()
    assert not await rows(env, MockEmailReceipt)
    at(env, 20)
    await drain(w)
    assert len(await rows(env, MockEmailReceipt)) == 1


@pytest.mark.asyncio
async def test_matching_notification_first_only(analysis_env):
    from test_matching_service import setup, drain as match_drain
    from model import MatchCandidate
    from service.text_analysis import request_item_reevaluation

    env = analysis_env
    await setup(env)
    await match_drain(env)
    async with env.factory() as db:
        candidate = await db.scalar(select(MatchCandidate))
        notification = await db.scalar(select(Notification))
        assert notification.event_id == candidate.id
        assert notification.recipient_id == env.ids['member']
        assert candidate.first_notified_at == notification.created_at
        assert await db.scalar(select(func.count()).select_from(EmailDeliveryItem)) == 1
    async with env.factory() as db, db.begin():
        await request_item_reevaluation(db, item=await db.get(FoundItem, env.ids['item']), now=env.clock())
    await match_drain(env)
    async with env.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 1
        assert await db.scalar(select(func.count()).select_from(EmailDeliveryItem)) == 1


@pytest.mark.asyncio
async def test_old_unsent_digest_merges_into_today_before_send(mail_env):
    env = mail_env
    env.settings = replace(env.settings, daily_limit=1)
    await add(env)
    at(env, 20)
    w = worker(env)
    await w.schedule(env.ids['finder'])
    old = (await rows(env, EmailDelivery))[0]
    env.clock.advance(days=1)
    await add(env)
    # Reproduce a separately prepared current-day digest without sending it.
    async with env.factory() as db, db.begin():
        policy = await w.policy(db, env.clock())
        current = EmailDelivery(recipient_id=env.ids['finder'], delivery_date=policy.delivery_date,
                                kind='DIGEST', slot_no=1, status='PENDING', attempts=0,
                                next_attempt_at=env.clock(), created_at=env.clock())
        db.add(current)
        await db.flush()
        latest = await db.scalar(select(EmailDeliveryItem).where(EmailDeliveryItem.status == 'PENDING'))
        latest.status, latest.delivery_id = 'QUEUED', current.id
    await drain(w)
    deliveries = await rows(env, EmailDelivery)
    assert next(d for d in deliveries if d.id == old.id).status == 'CANCELLED'
    assert len(await rows(env, MockEmailReceipt)) == 1
    assert all(e.status == 'SENT' for e in await rows(env, EmailDeliveryItem))
