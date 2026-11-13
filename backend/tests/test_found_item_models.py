"""Registration model boundaries, including conditional storage fields."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from schema.found_items import CreateFoundItemRequest


@pytest.fixture
def body():
    return dict(
        categoryId=str(uuid4()), title=' wallet ', description=' black wallet ',
        foundBuildingId=str(uuid4()), foundLocationDescription=' lobby ',
        foundAt='2026-11-03T10:00:00+09:00',
        photos=[dict(photoId=str(uuid4()), altText=' wallet ')],
        dropOff=dict(mode='KEPT_BY_FINDER'),
    )


@pytest.mark.parametrize('patch', [
    {'title': 'x' * 101}, {'description': 'x' * 2001}, {'foundLocationDescription': 'x' * 301},
    {'title': 1}, {'foundAt': 0}, {'foundAt': '2026-11-03T00:00:00'},
    {'dropOff': {'mode': 'KEPT_BY_FINDER', 'buildingId': None}},
    {'dropOff': {'mode': 'DROP_OFF', 'buildingId': str(uuid4()), 'spotDescription': None}},
])
def test_invalid(body, patch):
    with pytest.raises(ValidationError):
        CreateFoundItemRequest.model_validate({**body, **patch})


def test_required_fields_and_unique_photos(body):
    for key in body:
        with pytest.raises(ValidationError):
            CreateFoundItemRequest.model_validate({name: value for name, value in body.items() if name != key})
    parsed = CreateFoundItemRequest.model_validate(body)
    assert parsed.title == 'wallet' and parsed.photos[0].alt_text == 'wallet'
    for count in (0, 2, 6):
        with pytest.raises(ValidationError):
            CreateFoundItemRequest.model_validate({**body, 'photos': body['photos'] * count})
    with pytest.raises(ValidationError):
        CreateFoundItemRequest.model_validate({**body, 'dropOff': dict(
            mode='DROP_OFF', buildingId=body['foundBuildingId'], spotDescription='Desk', photo=body['photos'][0],
        )})
