"""All-word subscription HTTP and durable registration integration tests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, insert, select, text, update

from library.keyword_subscription_matching import all_terms_match, atomic_terms
from library.text_analysis_types import AnalysisError, AnalysisResult
from model import (
    EmailDeliveryItem, FoundItem, KeywordRegistrationEvent, KeywordSubscription,
    KeywordSubscriptionFeature, Notification, NotificationKeywordSource, NotificationSetting,
)
from router.auth import router as auth_router
from router.keyword_subscriptions import router
from service.keyword_worker import KeywordWorker
from service.text_analysis_profiles import initialize_policy
from test_analysis_worker import PROFILE
from test_profile_contract import assert_error, login
from test_schema import seed


BASE = '/api/v1/me/keyword-subscriptions'


class Runtime:
    profile = PROFILE

    def __init__(self):
        self.calls = 0
        self.error = None
        self.hook = None

    async def analyze(self, value):
        self.calls += 1
        if self.hook:
            await self.hook()
        if self.error:
            raise self.error
        words = (value.description + ' ' + (value.title or '')).lower().split()
        keywords = tuple('lemma:' + word for word in words if word not in {'the', 'a', 'item'})
        return AnalysisResult('EN', value.source_hash, value.canonical(),
                              keywords + ('phrase:black wallet', 'wn:wallet.n.01'), {}, PROFILE['fingerprint'])


@pytest.fixture
def env(auth_runtime):
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE categories, buildings, matching_runtime, matching_policies, text_analysis_profiles CASCADE'))
        ids = seed.__wrapped__(db)
        # This is a pre-feature existing item: no backfill registration is permitted.
        db.execute(delete(KeywordRegistrationEvent))
    runtime = Runtime()

    async def initialize():
        async with auth_runtime.factory() as db, db.begin():
            await initialize_policy(db, runtime.profile, now=auth_runtime.clock())
    asyncio.run(initialize())
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.state.text_analysis_runtime = runtime
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(router, prefix='/api/v1')
    with TestClient(app, base_url='https://testserver') as client:
        yield SimpleNamespace(client=client, rt=auth_runtime, runtime=runtime, ids=ids, app=app)
    with auth_runtime.sync_engine.begin() as db:
        db.execute(text('TRUNCATE categories, buildings, matching_runtime, matching_policies, text_analysis_profiles CASCADE'))


def subscribe(env, keyword='black wallet'):
    logged = login(env.client)
    result = env.client.post(BASE, json={'keyword': keyword}, headers={'X-CSRF-Token': logged['csrfToken']})
    assert result.status_code == 201, result.text
    return result.json(), logged


def new_item(env, description='black coin wallet'):
    item_id = uuid4()
    with env.rt.sync_engine.begin() as db:
        db.execute(insert(FoundItem).values(
            id=item_id, finder_id=env.ids['finder'], category_id=env.ids['category'],
            found_building_id=env.ids['building'], title='Item', description=description,
            found_location_description='PRIVATE', found_at=env.rt.clock(),
            expires_at=env.rt.clock() + timedelta(days=30),
        ))
    return item_id


def work(env):
    # Trigger timestamps use the real database clock, while auth tests have a fixed clock.
    return KeywordWorker(env.runtime, env.rt.factory)


@pytest.mark.parametrize('required,actual,expected', [
    (['lemma:black', 'lemma:wallet'], ['lemma:black', 'lemma:bag'], False),
    (['lemma:black', 'lemma:wallet'], ['lemma:black', 'lemma:coin', 'lemma:wallet'], True),
    (['lemma:black', 'lemma:wallet'], ['lemma:wallet'], False),
    ([], ['lemma:wallet'], False),
    (['lemma:sofa', 'wn:sofa.n.01'], ['lemma:couch', 'wn:sofa.n.01'], False),
    (['lemma:wallet', 'phrase:black wallet'], ['lemma:wallet'], True),
    (['identifier:a1', 'number:5'], ['identifier:a1', 'number:5'], True),
])
def test_all_terms(required, actual, expected):
    assert all_terms_match(required, actual) is expected


def test_api_create_list_duplicate_delete_and_isolation(env):
    body, logged = subscribe(env, '  Black wallet  ')
    assert body['keyword'] == 'Black wallet'
    assert set(body) == {'subscriptionId', 'keyword', 'createdAt'}
    assert body['createdAt'].endswith('+09:00')
    headers = {'X-CSRF-Token': logged['csrfToken']}
    assert_error(env.client.post(BASE, json={'keyword': 'ＢＬＡＣＫ wallet'}, headers=headers),
                 409, 'KEYWORD_ALREADY_SUBSCRIBED')
    page = env.client.get(BASE).json()
    assert page['items'] == [body] and page['totalElements'] == 1
    assert env.client.get(BASE + '?page=9').json()['items'] == []
    login(env.client, 'ADMIN')
    assert env.client.get(BASE).json()['items'] == []
    admin_csrf = env.client.get('/api/v1/auth/csrf').json()['csrfToken']
    assert_error(env.client.delete(BASE + '/' + body['subscriptionId'], headers={'X-CSRF-Token': admin_csrf}),
                 404, 'KEYWORD_SUBSCRIPTION_NOT_FOUND')
    logged = login(env.client)
    response = env.client.delete(BASE + '/' + body['subscriptionId'], headers={'X-CSRF-Token': logged['csrfToken']})
    assert response.status_code == 204 and response.content == b''


@pytest.mark.parametrize('body', [{}, {'keyword': None}, {'keyword': 1}, {'keyword': ' '},
    {'keyword': 'x' * 51}, {'keyword': 'wallet', 'userId': 'x'}])
def test_invalid_input(env, body):
    logged = login(env.client)
    assert_error(env.client.post(BASE, json=body, headers={'X-CSRF-Token': logged['csrfToken']}),
                 400, 'VALIDATION_ERROR')
    assert env.client.get(BASE).json()['totalElements'] == 0


def test_auth_security_and_query(env):
    assert_error(env.client.get(BASE), 401, 'AUTH_REQUIRED')
    assert_error(env.client.post(BASE, json={'keyword': 'wallet'}), 401, 'AUTH_REQUIRED')
    logged = login(env.client)
    headers = {'X-CSRF-Token': logged['csrfToken']}
    assert_error(env.client.post(BASE, json={'keyword': 'wallet'}), 403, 'CSRF_INVALID')
    assert_error(env.client.post(BASE, json={'keyword': 'wallet'}, headers={**headers, 'Origin': 'https://evil.example'}),
                 403, 'ORIGIN_NOT_ALLOWED')
    assert_error(env.client.post(BASE, content='{', headers={**headers, 'Content-Type': 'application/json'}),
                 400, 'MALFORMED_JSON')
    assert_error(env.client.post(BASE, content='x', headers=headers), 415, 'UNSUPPORTED_MEDIA_TYPE')
    for query in ['size=101', 'page=-1', 'userId=x']:
        assert_error(env.client.get(BASE + '?' + query), 400, 'VALIDATION_ERROR')
    assert env.runtime.calls == 0


@pytest.mark.parametrize('code', ['ANALYSIS_BUSY', 'ANALYSIS_TIMEOUT'])
def test_analysis_failure_is_atomic(env, code):
    logged = login(env.client)
    env.runtime.error = AnalysisError(code)
    result = env.client.post(BASE, json={'keyword': 'wallet'}, headers={'X-CSRF-Token': logged['csrfToken']})
    assert_error(result, 503, 'KEYWORD_ANALYSIS_UNAVAILABLE')
    assert result.headers['Retry-After'] == '5'
    assert env.client.get(BASE).json()['items'] == []


def test_empty_terms_and_disabled(env):
    logged = login(env.client)
    headers = {'X-CSRF-Token': logged['csrfToken']}
    result = env.client.post(BASE, json={'keyword': 'the'}, headers=headers)
    assert_error(result, 400, 'VALIDATION_ERROR')
    assert result.json()['fieldErrors'][0]['code'] == 'NO_MATCHABLE_TERMS'
    env.app.state.text_analysis_runtime = None
    assert_error(env.client.post(BASE, json={'keyword': 'wallet'}, headers=headers), 503, 'KEYWORD_ANALYSIS_UNAVAILABLE')


def test_inference_releases_locks_and_reauthenticates(env):
    logged = login(env.client)

    async def expire_session():
        async with env.rt.factory() as db, db.begin():
            # This would block if POST retained its session lock during inference.
            await db.execute(text("SET LOCAL lock_timeout = '500ms'"))
            await db.execute(text('UPDATE sessions SET absolute_expires_at=:now'), {'now': env.rt.clock()})
    env.runtime.hook = expire_session
    result = env.client.post(BASE, json={'keyword': 'wallet'}, headers={'X-CSRF-Token': logged['csrfToken']})
    assert_error(result, 401, 'SESSION_EXPIRED')
    with env.rt.sync_engine.connect() as db:
        assert db.scalar(select(func.count()).select_from(KeywordSubscription)) == 0


def test_concurrent_duplicate(env):
    logged = login(env.client)
    headers = {'X-CSRF-Token': logged['csrfToken']}
    def create(_):
        return env.client.post(BASE, json={'keyword': 'wallet'}, headers=headers).status_code
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(create, range(2))) == [201, 409]


@pytest.mark.asyncio
async def test_snapshot_all_terms_and_multiple_sources(env):
    first, logged = subscribe(env)
    second, logged = subscribe(env, 'wallet')
    item_id = new_item(env)
    # Snapshot survives edits before analysis.
    with env.rt.sync_engine.begin() as db:
        db.execute(update(FoundItem).where(FoundItem.id == item_id).values(description='black bag'))
    worker = work(env)
    assert await worker.run_once()
    assert not await worker.run_once()
    async with env.rt.factory() as db:
        event = await db.scalar(select(KeywordRegistrationEvent))
        assert event.status == 'DONE' and event.source_description is None
        notifications = list((await db.scalars(select(Notification))).all())
        assert len(notifications) == 1 and notifications[0].type == 'KEYWORD_MATCH'
        sources = list((await db.scalars(select(NotificationKeywordSource.subscription_id))).all())
        assert set(sources) == {UUID(first['subscriptionId']), UUID(second['subscriptionId'])}
        assert await db.scalar(select(func.count()).select_from(EmailDeliveryItem)) == 1
    from service.email_worker import EmailWorker
    from library.notification_settings import NotificationSettings
    email = EmailWorker(env.rt.factory, NotificationSettings.from_environment())
    async with env.rt.factory() as db:
        notification = await db.scalar(select(Notification))
        assert await email.eligible(db, notification, worker.clock())
    # Remove all sources: pending delivery becomes ineligible, in-app remains.
    for body in (first, second):
        result = env.client.delete(BASE + '/' + body['subscriptionId'], headers={'X-CSRF-Token': logged['csrfToken']})
        assert result.status_code == 204
        async with env.rt.factory() as db:
            notification = await db.scalar(select(Notification))
            assert await email.eligible(db, notification, worker.clock()) is (body is first)


@pytest.mark.asyncio
async def test_no_match_no_retroactive_and_no_edit_event(env):
    subscribe(env)
    item_id = new_item(env, 'black bag')
    new_item(env, 'red coin')
    subscribe(env, 'red')  # Too late for both registration events.
    worker = work(env)
    while await worker.run_once():
        pass
    async with env.rt.factory() as db, db.begin():
        assert await db.scalar(select(func.count()).select_from(Notification)) == 0
        await db.execute(update(FoundItem).where(FoundItem.id == item_id).values(description='black wallet'))
        assert await db.scalar(select(func.count()).select_from(KeywordRegistrationEvent)) == 2
    assert not await worker.run_once()


@pytest.mark.asyncio
async def test_lease_fence_retry_and_hidden_cancellation(env):
    subscribe(env)
    item_id = new_item(env)
    worker = work(env)
    event = await worker.claim()
    assert event and await worker.claim() is None
    async with env.rt.factory() as db, db.begin():
        await db.execute(update(KeywordRegistrationEvent).values(lease_until=worker.clock() - timedelta(seconds=1)))
    assert not await worker.prepare(event)
    replacement = await worker.claim()
    assert replacement.lease_token != event.lease_token
    await worker.fail(event, 'STALE')
    async with env.rt.factory() as db:
        assert (await db.get(KeywordRegistrationEvent, event.id)).attempts == 0
    await worker.fail(replacement, 'ANALYSIS_TIMEOUT')
    async with env.rt.factory() as db, db.begin():
        current = await db.get(KeywordRegistrationEvent, event.id)
        assert current.attempts == 1 and current.lease_token is None
        current.next_attempt_at = worker.clock()
    assert await worker.run_once()
    async with env.rt.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 1
    hidden_id = new_item(env)
    async with env.rt.factory() as db, db.begin():
        await db.execute(update(FoundItem).where(FoundItem.id == hidden_id).values(hidden=True))
    assert not await worker.run_once()


@pytest.mark.asyncio
async def test_delete_while_analyzing_and_email_off(env):
    body, logged = subscribe(env)
    new_item(env)
    async def delete_subscription():
        async with env.rt.factory() as db, db.begin():
            await db.execute(delete(KeywordSubscription).where(KeywordSubscription.id == UUID(body['subscriptionId'])))
    env.runtime.hook = delete_subscription
    assert await work(env).run_once()
    async with env.rt.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 0
    env.runtime.hook = None
    body, logged = subscribe(env)
    with env.rt.sync_engine.begin() as db:
        db.execute(insert(NotificationSetting).values(user_id=UUID(logged['user']['userId']), keyword_email=False))
    new_item(env)
    assert await work(env).run_once()
    async with env.rt.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 1
        assert await db.scalar(select(func.count()).select_from(EmailDeliveryItem)) == 0


def test_openapi_and_location(env):
    logged = login(env.client)
    result = env.client.post(BASE, json={'keyword': 'wallet'}, headers={'X-CSRF-Token': logged['csrfToken']})
    assert result.headers['Location'] == BASE + '/' + result.json()['subscriptionId']
    spec = env.app.openapi()['paths'][BASE]
    assert '503' in spec['post']['responses']
    assert spec['post']['requestBody']['required']


@pytest.mark.asyncio
async def test_missing_features_reanalysis_concurrent_workers_and_event_replay(env):
    subscribe(env)
    with env.rt.sync_engine.begin() as db:
        db.execute(delete(KeywordSubscriptionFeature))
    new_item(env)
    workers = [work(env), work(env)]
    await asyncio.gather(*(worker.run_once() for worker in workers))
    async with env.rt.factory() as db, db.begin():
        event = await db.scalar(select(KeywordRegistrationEvent))
        assert event.status == 'DONE'
        assert await db.scalar(select(func.count()).select_from(KeywordSubscriptionFeature)) == 1
        assert await db.scalar(select(func.count()).select_from(Notification)) == 1
        # Simulate replay of the complete recipient batch after uncertain completion.
        event.status, event.cursor_user_id, event.completed_at = 'READY', None, None
    assert await work(env).run_once()
    async with env.rt.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 1
        assert await db.scalar(select(func.count()).select_from(EmailDeliveryItem)) == 1


@pytest.mark.asyncio
async def test_atomic_registration_rollback_and_maintenance(env):
    from service.keyword_maintenance import cleanup, retry_event
    subscribe(env)
    item_id = uuid4()
    async with env.rt.factory() as db, db.begin():
        db.add(FoundItem(
            id=item_id, finder_id=env.ids['finder'], category_id=env.ids['category'],
            found_building_id=env.ids['building'], title='Item', description='wallet',
            found_location_description='PRIVATE', found_at=env.rt.clock(),
            expires_at=env.rt.clock() + timedelta(days=30),
        ))
        await db.flush()
        assert await db.scalar(select(KeywordRegistrationEvent.id).where(KeywordRegistrationEvent.item_id == item_id))
        await db.rollback()
    async with env.rt.factory() as db:
        assert await db.scalar(select(func.count()).select_from(KeywordRegistrationEvent)) == 0
    new_item(env)
    worker = work(env)
    async with env.rt.factory() as db, db.begin():
        event = await db.scalar(select(KeywordRegistrationEvent))
        event.status, event.failed_at, event.last_error_code = 'FAILED', worker.clock(), 'ANALYSIS_TIMEOUT'
        event.attempts = 10
        event_id = event.id
    async with env.rt.factory() as db, db.begin():
        await retry_event(db, event_id, now=worker.clock())
    assert await worker.run_once()
    async with env.rt.factory() as db, db.begin():
        event = await db.get(KeywordRegistrationEvent, event_id)
        assert event.status == 'DONE'
        await cleanup(db, now=worker.clock() + timedelta(days=8))
        await db.refresh(event)
        assert event.terms is None
    new_item(env)
    async with env.rt.factory() as db, db.begin():
        assert await cleanup(db, now=worker.clock() + timedelta(days=31)) == 1
    assert not await worker.run_once()


@pytest.mark.asyncio
async def test_lease_expiry_rolls_back_notification_batch(env, monkeypatch):
    import service.keyword_worker as module
    subscribe(env)
    new_item(env)
    worker = work(env)
    event = await worker.claim()
    assert await worker.prepare(event)
    original = module.create_notification
    now = worker.clock()

    async def expire_after_insert(*args, **kwargs):
        await original(*args, **kwargs)
        worker.clock = lambda: now + timedelta(seconds=121)
    monkeypatch.setattr(module, 'create_notification', expire_after_insert)
    assert not await worker.recipient(event)
    async with env.rt.factory() as db:
        assert await db.scalar(select(func.count()).select_from(Notification)) == 0
        assert (await db.get(KeywordRegistrationEvent, event.id)).cursor_user_id is None


@pytest.mark.asyncio
async def test_profile_switch_drains_events_and_create_rejects_mismatch(env):
    from sqlalchemy.exc import DBAPIError
    from model import MatchingPolicy, MatchingRuntime, TextAnalysisProfile
    from service.text_analysis_profiles import POLICY_CONFIG, POLICY_RULE, fingerprint
    subscribe(env)
    new_item(env)
    alternate = {key: value for key, value in PROFILE.items() if key != 'fingerprint'}
    alternate['runtime_config'] = {'test': 'alternate'}
    alternate['fingerprint'] = fingerprint(alternate)
    profile_id, policy_id = uuid4(), uuid4()
    async with env.rt.factory() as db, db.begin():
        await db.execute(insert(TextAnalysisProfile).values(id=profile_id, name='alternate', **alternate))
        await db.execute(insert(MatchingPolicy).values(
            id=policy_id, analysis_profile_id=profile_id, rule_version=POLICY_RULE, config=POLICY_CONFIG,
            fingerprint=fingerprint({'analysis_profile_fingerprint': alternate['fingerprint'],
                                     'rule_version': POLICY_RULE, 'config': POLICY_CONFIG}),
        ))
    with pytest.raises(DBAPIError):
        async with env.rt.factory() as db, db.begin():
            await db.execute(update(MatchingRuntime).values(active_policy_id=policy_id))
    assert await work(env).run_once()
    async with env.rt.factory() as db, db.begin():
        await db.execute(update(MatchingRuntime).values(active_policy_id=policy_id))
    logged = login(env.client)
    assert_error(env.client.post(BASE, json={'keyword': 'blue bag'}, headers={'X-CSRF-Token': logged['csrfToken']}),
                 503, 'KEYWORD_ANALYSIS_UNAVAILABLE')


@pytest.mark.asyncio
async def test_periodic_cleanup_works_without_analysis_runtime(env):
    from service.notification_worker import NotificationWorker
    new_item(env)
    now = work(env).clock() + timedelta(days=31)
    worker = NotificationWorker(env.rt.factory, clock=lambda: now)
    await worker.cleanup_keywords()
    async with env.rt.factory() as db:
        event = await db.scalar(select(KeywordRegistrationEvent))
        assert event.status == 'CANCELLED' and event.source_description is None
        assert event.last_error_code == 'KEYWORD_SNAPSHOT_EXPIRED'
    assert worker.next_keyword_cleanup == now + timedelta(hours=1)
