"""MATCH-01 authentication, filtering and read-only HTTP contract."""
import asyncio
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import text

from main import app as full_app
from test_admin_contract import error, login
from test_analysis_worker import analysis_env
from test_matching_service import setup, drain


@pytest.fixture
def matching_client(analysis_env, auth_runtime):
    env = analysis_env
    asyncio.run(setup(env))
    asyncio.run(drain(env))
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.router.routes.extend(full_app.routes)
    with TestClient(app, base_url='https://testserver') as client:
        member_id, _ = login(client, 'student-01')
        with env.sync.begin() as db:
            db.execute(text('UPDATE lost_reports SET owner_id=:owner WHERE id=:id'),
                       {'owner': member_id, 'id': env.ids['report']})
        yield client, env


def path(env):
    return f"/api/v1/lost-reports/{env.ids['report']}/matches"


def test_http_response_private_fields_and_get_has_no_matching_side_effects(matching_client):
    client, env = matching_client
    tables = ('match_candidates', 'match_evaluation_jobs', 'found_item_text_features',
              'lost_report_text_features', 'outbox_events', 'notifications')

    def snapshot():
        with env.sync.connect() as db:
            return [db.execute(text(f'SELECT coalesce(jsonb_agg(to_jsonb(t) ORDER BY id), \'[]\'::jsonb) FROM {t} t')).scalar_one()
                    for t in tables]

    before = snapshot()
    response = client.get(path(env), headers={'Accept-Language': 'en'})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result['isComplete'] and result['totalElements'] == 1
    assert result['items'][0]['matchedBy'] == ['BUILDING', 'KEYWORD']
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['content-language'] == 'en'
    assert result['items'][0]['matchedAt'].endswith('+09:00')
    assert set(result['items'][0]['item']) == {
        'itemId', 'categoryId', 'foundBuildingId', 'title', 'foundAt', 'status', 'sensitive',
    }
    assert 'SECRET' not in response.text
    assert snapshot() == before


def test_owner_admin_and_existence_hiding(matching_client):
    client, env = matching_client
    login(client, 'faculty-01')
    foreign = client.get(path(env))
    error(foreign, 404, 'LOST_REPORT_NOT_FOUND')
    missing = client.get(f'/api/v1/lost-reports/{uuid4()}/matches')
    assert missing.json() == foreign.json()
    login(client, 'admin-01')
    assert client.get(path(env)).status_code == 200
    client.cookies.clear()
    error(client.get(path(env)), 401, 'AUTH_REQUIRED')


@pytest.mark.parametrize('query', ['page=-1', 'size=0', 'size=101', 'page=abc', 'ownerId=x'])
def test_query_validation(matching_client, query):
    client, env = matching_client
    error(client.get(path(env) + '?' + query), 400, 'VALIDATION_ERROR')


def test_hidden_visibility_count_and_admin_access(matching_client):
    client, env = matching_client
    with env.sync.begin() as db:
        db.execute(text('UPDATE found_items SET hidden=true WHERE id=:id'), {'id': env.ids['item']})
    member = client.get(path(env)).json()
    assert member['totalElements'] == member['totalPages'] == 0 and member['items'] == []
    login(client, 'admin-01')
    admin = client.get(path(env)).json()
    assert admin['totalElements'] == 1 and len(admin['items']) == 1


def test_openapi_contract():
    route = full_app.openapi()['paths']['/api/v1/lost-reports/{reportId}/matches']['get']
    assert '501' not in route['responses']
    assert route['responses']['200']['content']['application/json']['schema']['$ref'].endswith('/MatchCandidatePage')
    names = {p['name'] for p in route['parameters']}
    assert names == {'reportId', 'page', 'size', 'KAIFIND_SESSION', 'Accept-Language'}
