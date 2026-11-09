"""Strict JSON input validation for notification mutations."""

import pytest
from pydantic import ValidationError

from schema.notifications import UpdateNotificationRequest, UpdateNotificationSettingsRequest


FIELDS = ['emailEnabled', 'matchEmail', 'collectionEmail', 'expiryEmail', 'keywordEmail']


@pytest.mark.parametrize('field', FIELDS)
@pytest.mark.parametrize('value', [None, 0, 1, 'true', 'false', [], {}])
def test_settings_reject_non_boolean(field, value):
    body = dict.fromkeys(FIELDS, True)
    body[field] = value
    with pytest.raises(ValidationError):
        UpdateNotificationSettingsRequest.model_validate(body)


@pytest.mark.parametrize('field', FIELDS)
def test_settings_require_every_field(field):
    body = dict.fromkeys(FIELDS, True)
    del body[field]
    with pytest.raises(ValidationError):
        UpdateNotificationSettingsRequest.model_validate(body)


@pytest.mark.parametrize('value', [False, None, 0, 1, 'true', 'false', [], {}])
def test_read_requires_literal_json_true(value):
    with pytest.raises(ValidationError):
        UpdateNotificationRequest.model_validate({'read': value})
