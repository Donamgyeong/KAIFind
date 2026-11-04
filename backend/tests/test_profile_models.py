"""Profile request validation and published API contracts."""

import pytest
from fastapi import FastAPI
from pydantic import ValidationError

from router.profile import router
from schema.profile import UpdateProfileRequest


@pytest.mark.parametrize('value,expected', [('ko', 'ko'), ('en', 'en'), (' en \n', 'en')])
def test_language_normalization(value, expected):
    assert UpdateProfileRequest(language=value).language == expected


@pytest.mark.parametrize('body', [
    {}, {'language': None}, {'language': True}, {'language': 1},
    {'language': []}, {'language': {}}, {'language': ''},
    {'language': '  '}, {'language': 'EN'}, {'language': 'ja'},
    *[{'language': 'en', field: 'changed'}
      for field in ('userId', 'name', 'email', 'affiliation', 'role')],
])
def test_invalid_profile_request(body):
    with pytest.raises(ValidationError):
        UpdateProfileRequest.model_validate(body)


def test_openapi_contract():
    app = FastAPI()
    app.include_router(router, prefix='/api/v1')
    spec = app.openapi()
    operations = spec['paths']['/api/v1/me/profile']
    for method in ('get', 'patch'):
        operation = operations[method]
        assert operation['responses']['200']['content']['application/json']['schema'] == {
            '$ref': '#/components/schemas/ProfileResponse',
        }
        assert '501' not in operation['responses']
        parameters = {p['name']: p for p in operation['parameters']}
        assert parameters['KAIFIND_SESSION']['required'] is True
        assert 'Accept-Language' in parameters
    assert parameters['X-CSRF-Token']['required'] is True
    assert operations['patch']['requestBody']['required'] is True
    model = spec['components']['schemas']['UpdateProfileRequest']
    assert model['required'] == ['language']
    assert model['additionalProperties'] is False
