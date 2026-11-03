"""Auth wire validation, independent of the unimplemented service layer."""
import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from schema.auth import AuthUserResponse, MockAccountListResponse, MockLoginRequest, SessionInfo


@pytest.mark.parametrize('key', ['a', '0', 'student-01', 'a_b-1', 'a' * 64])
def test_account_key_boundaries(key):
    assert MockLoginRequest.model_validate({'mockAccountId': key}).mock_account_id == key


@pytest.mark.parametrize('value', [None, 1, True, [], {}, '', 'a' * 65, 'Student',
                                     ' student', 'student ', 'a/b', '_a', '-a', '학생', 'a\n'])
def test_invalid_account_key(value):
    with pytest.raises(ValidationError):
        MockLoginRequest.model_validate({'mockAccountId': value})


def test_missing_account_key():
    with pytest.raises(ValidationError) as exc:
        MockLoginRequest.model_validate({})
    assert exc.value.errors()[0]['type'] == 'missing'


@pytest.mark.parametrize('field', ['role', 'email', 'name', 'userId', 'affiliation'])
def test_login_rejects_identity_and_role_injection(field):
    with pytest.raises(ValidationError) as exc:
        MockLoginRequest.model_validate({'mockAccountId': 'student-01', field: 'ADMIN'})
    assert any(e['loc'] == (field,) and e['type'] == 'extra_forbidden' for e in exc.value.errors())


def test_user_response_wire_types():
    data = dict(userId='c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed', name='테스트 학생',
                email='student01@example.com', affiliation='STUDENT', role='MEMBER', language='ko')
    assert json.loads(AuthUserResponse.model_validate(data).model_dump_json()) == data


@pytest.mark.parametrize('field,value', [('userId', 'bad'), ('email', 'bad'),
    ('affiliation', 'GUEST'), ('role', 'GUEST'), ('language', 'ja')])
def test_user_response_rejects_invalid_types(field, value):
    data = dict(userId='c0f4c2d2-0e5c-4b41-bd40-7ec14f8bb8ed', name='테스트',
                email='student01@example.com', affiliation='STUDENT', role='MEMBER', language='ko')
    data[field] = value
    with pytest.raises(ValidationError):
        AuthUserResponse.model_validate(data)


def test_session_serializes_utc_as_kst():
    info = SessionInfo.model_validate(dict(idleTimeoutSeconds=1800,
        idleExpiresAt=datetime(2026, 11, 3, 1, 30, tzinfo=timezone.utc),
        absoluteExpiresAt=datetime(2026, 11, 3, 13, tzinfo=timezone.utc)))
    data = json.loads(info.model_dump_json())
    assert data['idleExpiresAt'] == '2026-11-03T10:30:00+09:00'
    assert data['absoluteExpiresAt'] == '2026-11-03T22:00:00+09:00'


def test_session_rejects_naive_timestamp():
    with pytest.raises(ValidationError):
        SessionInfo.model_validate(dict(idleTimeoutSeconds=1800,
            idleExpiresAt='2026-11-03T10:30:00', absoluteExpiresAt='2026-11-03T22:00:00+09:00'))


def test_empty_accounts_is_an_array():
    assert MockAccountListResponse(accounts=[]).model_dump() == {'accounts': []}
