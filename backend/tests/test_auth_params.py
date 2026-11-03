"""Regression checks for dependency parsing and the published Auth contract."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.auth import router


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    return app


@pytest.mark.parametrize('method,path', [('get', '/me'), ('post', '/logout'), ('post', '/mock/login')])
def test_missing_required_cookie_is_a_validation_response_not_a_server_error(app, method, path):
    with TestClient(app) as client:
        response = client.request(method, '/api/v1/auth' + path)
    # Temporary default FastAPI behavior; service implementation will replace this
    # with 401/403 according to the acceptance tests in test_auth_contract.py.
    assert response.status_code == 422
    assert any(e['loc'] == ['cookie', 'KAIFIND_SESSION'] for e in response.json()['detail'])


def test_openapi_documents_transport_parameters(app):
    operation = app.openapi()['paths']['/api/v1/auth/mock/login']['post']
    parameters = {(p['in'], p['name']): p for p in operation['parameters']}
    for key in [('cookie', 'KAIFIND_SESSION'), ('header', 'X-CSRF-Token'), ('header', 'Content-Type')]:
        assert parameters[key]['required'] is True
    for key in [('header', 'Accept-Language'), ('header', 'Origin')]:
        assert parameters[key]['required'] is False
    assert not any(p['in'] in {'query', 'path'} for p in operation['parameters'])
    assert 'application/json' in operation['requestBody']['content']


def test_openapi_logout_has_no_success_body(app):
    response = app.openapi()['paths']['/api/v1/auth/logout']['post']['responses']['204']
    assert 'content' not in response
