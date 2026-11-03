"""Regression checks for dependency parsing and the published Auth contract."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from router.auth import router


@pytest.fixture
def app(auth_runtime):
    app = FastAPI()
    app.state.auth_runtime = auth_runtime
    app.include_router(router, prefix='/api/v1')
    return app


@pytest.mark.parametrize('method,path,status,code', [
    ('get', '/me', 401, 'AUTH_REQUIRED'),
    ('post', '/logout', 403, 'CSRF_INVALID'),
    ('post', '/mock/login', 403, 'CSRF_INVALID'),
])
def test_missing_cookie_returns_auth_error(app, method, path, status, code):
    with TestClient(app, base_url='https://testserver') as client:
        kwargs = {'json': {'mockAccountId': 'student-01'}} if path == '/mock/login' else {}
        response = client.request(method, '/api/v1/auth' + path, **kwargs)
    assert response.status_code == status
    assert response.json()['code'] == code


def test_openapi_documents_transport_parameters(app):
    operation = app.openapi()['paths']['/api/v1/auth/mock/login']['post']
    parameters = {(p['in'], p['name']): p for p in operation['parameters']}
    for key in [('cookie', 'KAIFIND_SESSION'), ('header', 'X-CSRF-Token'), ('header', 'Content-Type')]:
        assert parameters[key]['required'] is True
    for key in [('header', 'Accept-Language'), ('header', 'Origin')]:
        assert parameters[key]['required'] is False
    assert not any(p['in'] in {'query', 'path'} for p in operation['parameters'])
    assert 'application/json' in operation['requestBody']['content']
    assert '422' not in operation['responses']
    assert '400' in operation['responses']


def test_openapi_logout_has_no_success_body(app):
    response = app.openapi()['paths']['/api/v1/auth/logout']['post']['responses']['204']
    assert 'content' not in response
