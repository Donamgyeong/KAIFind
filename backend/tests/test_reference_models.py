"""Public reference schema and OpenAPI contracts."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from main import app
from schema.reference_params import BuildingParams
from schema.reference import BuildingCountSummary


def test_count_serialization_and_validation():
    fields = dict(buildingId=uuid4(), code='E3', nameKo='건물', nameEn='Building', active=True)
    assert 'postedCount' not in BuildingCountSummary(**fields).model_dump(exclude_none=True)
    assert BuildingCountSummary(**fields, postedCount=0).model_dump()['postedCount'] == 0
    with pytest.raises(ValidationError):
        BuildingCountSummary(**fields, postedCount=-1)
    with pytest.raises(ValidationError):
        BuildingParams(unknown=True)


def test_public_openapi():
    paths = app.openapi()['paths']
    for path in ('/api/v1/buildings', '/api/v1/categories'):
        operation = paths[path]['get']
        assert '501' not in operation['responses']
        assert {'200', '400', '500'} <= operation['responses'].keys()
        assert not operation.get('security')
        assert all(p['in'] != 'cookie' for p in operation.get('parameters', []))
    parameter = paths['/api/v1/buildings']['get']['parameters'][0]
    assert parameter['name'] == 'includePostedCount'
    assert parameter['schema']['default'] is False
