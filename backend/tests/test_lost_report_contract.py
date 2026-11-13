"""Lost report HTTP integration against the isolated PostgreSQL database."""

import asyncio
import os
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from router.auth import router as auth_router
from router.lost_reports import router
from test_analysis_worker import PROFILE, analysis_env
from test_profile_contract import login, assert_error
from service.text_analysis_profiles import initialize_policy


BASE = '/api/v1/lost-reports'


@pytest.fixture
def context(analysis_env, auth_runtime):
    env = analysis_env

    async def prepare():
        async with env.factory() as db, db.begin():
            await initialize_policy(db, PROFILE, now=env.clock())
    asyncio.run(prepare())
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.include_router(auth_router, prefix='/api/v1')
    app.include_router(router, prefix='/api/v1')
    with TestClient(app, base_url='https://testserver') as client:
        logged = login(client)
        body = {
            'categoryId': str(env.ids['category']), 'description': ' black wallet ',
            'possibleBuildingIds': [str(env.ids['building'])],
            'lostDateFrom': '2026-11-01', 'lostDateTo': '2026-11-02',
            'privateIdentifyingDetails': ' SECRET ',
        }
        yield client, env, body, {'X-CSRF-Token': logged['csrfToken']}


def create(context):
    client, env, body, headers = context
    response = client.post(BASE, json=body, headers=headers)
    assert response.status_code == 201, response.text
    assert response.headers['location'] == BASE + '/' + response.json()['reportId']
    return response.json(), response.headers['location']


def test_create_update_extend_resolve(context):
    client, env, body, headers = context
    report, path = create(context)
    assert report['description'] == 'black wallet'
    assert report['privateIdentifyingDetails'] == 'SECRET'
    assert report['analysisStatus'] == 'PENDING'
    assert client.get(path).json() == report
    page = client.get(BASE).json()
    assert page['totalElements'] == 1 and 'privateIdentifyingDetails' not in page['items'][0]
    with env.sync.connect() as db:
        assert db.execute(text('SELECT count(*) FROM lost_report_text_features WHERE report_id=:id'),
                          {'id': report['reportId']}).scalar_one() == 1
    changed = {**body, 'description': 'blue wallet'}
    response = client.put(path, json=changed, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['description'] == 'blue wallet'
    response = client.post(path + '/extend', headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['expiresAt'] != report['expiresAt']
    resolved = client.post(path + '/resolve', headers=headers)
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()['status'] == 'RESOLVED'
    assert resolved.json()['privateIdentifyingDetails'] is None
    assert client.post(path + '/resolve', headers=headers).json() == resolved.json()
    assert_error(client.put(path, json=body, headers=headers), 409, 'LOST_REPORT_NOT_OPEN')
    with env.sync.connect() as db:
        assert db.execute(text('SELECT count(*) FROM lost_report_private_details WHERE report_id=:id'),
                          {'id': report['reportId']}).scalar_one() == 0


@pytest.mark.parametrize('action', ['extend', 'update', 'detail', 'list'])
def test_expiry_commits_even_with_conflict(context, action):
    client, env, body, headers = context
    report, path = create(context)
    with env.sync.begin() as db:
        db.execute(text('UPDATE lost_reports SET expires_at=:now WHERE id=:id'),
                   {'now': env.clock(), 'id': report['reportId']})
    if action == 'extend':
        assert_error(client.post(path + '/extend', headers=headers), 409, 'LOST_REPORT_NOT_OPEN')
    elif action == 'update':
        assert_error(client.put(path, json=body, headers=headers), 409, 'LOST_REPORT_NOT_OPEN')
    elif action == 'detail':
        assert client.get(path).json()['status'] == 'CLOSED'
    else:
        assert client.get(BASE + '?status=CLOSED').json()['totalElements'] == 1
    closed = client.get(path).json()
    assert closed['privateIdentifyingDetails'] is None
    resolved = client.post(path + '/resolve', headers=headers).json()
    assert resolved['status'] == 'RESOLVED' and resolved['closedAt'] == closed['closedAt']


def test_admin_read_only_and_account_isolation(context):
    client, env, body, headers = context
    _, path = create(context)
    admin = login(client, 'ADMIN')
    headers = {'X-CSRF-Token': admin['csrfToken']}
    assert client.get(path).status_code == 200
    assert client.get(BASE).json()['totalElements'] == 0
    for suffix in ('extend', 'resolve'):
        assert_error(client.post(path + '/' + suffix, headers=headers), 404, 'LOST_REPORT_NOT_FOUND')
    assert_error(client.put(path, json=body, headers=headers), 404, 'LOST_REPORT_NOT_FOUND')
    assert_error(client.get(BASE + '/' + str(uuid4())), 404, 'LOST_REPORT_NOT_FOUND')


@pytest.mark.parametrize('patch', [
    {'description': ' '}, {'description': 1}, {'privateIdentifyingDetails': None},
    {'possibleBuildingIds': []}, {'lostDateFrom': '2026-11-03'},
    {'lostDateTo': '2099-01-01'}, {'extra': 'value'},
])
def test_validation(context, patch):
    client, env, body, headers = context
    assert_error(client.post(BASE, json={**body, **patch}, headers=headers), 400, 'VALIDATION_ERROR')
    assert client.get(BASE).json()['totalElements'] == 0


def test_inactive_reference_and_private_only_reevaluation(context):
    client, env, body, headers = context
    report, path = create(context)
    with env.sync.begin() as db:
        db.execute(text('UPDATE categories SET active=false WHERE id=:id'), {'id': body['categoryId']})
        db.execute(text('UPDATE buildings SET active=false WHERE id=:id'), {'id': body['possibleBuildingIds'][0]})
    assert_error(client.post(BASE, json=body, headers=headers), 400, 'INVALID_REFERENCE')
    response = client.put(path, json={**body, 'privateIdentifyingDetails': 'NEW SECRET'}, headers=headers)
    assert response.status_code == 200, response.text
    with env.sync.connect() as db:
        assert db.execute(text('SELECT count(*) FROM lost_report_text_features WHERE report_id=:id'),
                          {'id': report['reportId']}).scalar_one() == 1
        assert db.execute(text('SELECT requested_generation FROM match_evaluation_jobs WHERE report_id=:id'),
                          {'id': report['reportId']}).scalar_one() == 2


def test_security_and_query_contract(context):
    client, env, body, headers = context
    _, path = create(context)
    assert_error(client.post(path + '/extend', headers=headers, json={}), 400, 'VALIDATION_ERROR')
    assert_error(client.post(BASE, json=body), 403, 'CSRF_INVALID')
    for query in ('page=-1', 'size=101', 'ownerId=x', 'status=BAD'):
        assert_error(client.get(BASE + '?' + query), 400, 'VALIDATION_ERROR')
    client.cookies.clear()
    assert_error(client.get(BASE), 401, 'AUTH_REQUIRED')


def test_analysis_failure_rolls_back_creation(context, monkeypatch):
    client, env, body, headers = context

    async def fail(*args, **kwargs):
        raise RuntimeError('simulated request failure')
    monkeypatch.setattr('service.lost_reports.request_lost_report_analysis', fail)
    assert_error(client.post(BASE, json=body, headers=headers), 500, 'INTERNAL_SERVER_ERROR')
    assert client.get(BASE).json()['totalElements'] == 0


def test_concurrent_extend_and_resolve(context):
    from concurrent.futures import ThreadPoolExecutor

    client, env, body, headers = context
    report, path = create(context)
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(client.post, path + suffix, headers=headers)
                   for suffix in ('/extend', '/resolve')]
        responses = [future.result(timeout=20) for future in futures]
    assert responses[0].status_code in (200, 409)
    assert responses[1].status_code == 200, responses[1].text
    result = client.get(path).json()
    assert result['status'] == 'RESOLVED' and result['privateIdentifyingDetails'] is None


@pytest.mark.parametrize('real', [False, pytest.param(True, marks=pytest.mark.skipif(
    os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true', reason='Real model opt-in',
))])
def test_http_analysis_and_matching_pipeline(context, real):
    from model import FoundItem
    from service.text_analysis import request_found_item_analysis
    from test_analysis_worker import worker
    from test_matching_service import drain
    from service.matching import read_matches

    client, env, body, headers = context
    async def process():
        runtime = None
        try:
            if real:
                from library.translation_runtime import TranslationRuntime, TranslationSettings
                runtime = TranslationRuntime(TranslationSettings.from_environment())
                await runtime.start()
                env.runtime = runtime
                async with env.factory() as db, db.begin():
                    await db.execute(text('DELETE FROM matching_runtime'))
                    await initialize_policy(db, runtime.profile, now=env.clock())
                body['description'] = '검은 지갑입니다.'
            report, path = create(context)
            async with env.factory() as db, db.begin():
                item = await db.get(FoundItem, env.ids['item'])
                item.found_at = env.clock()
                item.title = 'Wallet'
                item.description = '검은 지갑입니다.'
                await db.flush()
                await request_found_item_analysis(db, item=item, now=env.clock())
            while await worker(env).run_once():
                pass
            await drain(env)
            async with env.factory() as db:
                from uuid import UUID
                result = await read_matches(
                    db, report_id=UUID(report['reportId']), now=env.clock(), internal=True,
                )
            return result, path
        finally:
            if runtime:
                await runtime.close()
    result, path = asyncio.run(process())
    assert result.is_complete and result.total_elements == 1
    if real:
        assert 'KEYWORD' in result.items[0].matched_by
    assert client.get(path).json()['matchingStatus'] == 'READY'
