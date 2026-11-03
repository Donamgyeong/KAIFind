"""Admin request validation and public serialization without a database."""
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from main import app
from schema.admin import (CreateBuildingRequest, CreateCategoryRequest, Page,
    StatisticsResponse, UpdateBuildingRequest, UpdateCategoryRequest,
    UpdateCollectionRestrictionRequest)
from service.audit import append_audit, one_year_after


@pytest.mark.parametrize('model,payload', [
    (UpdateBuildingRequest, {}), (UpdateBuildingRequest, {'active': None}),
    (UpdateBuildingRequest, {'active': 'false'}), (UpdateBuildingRequest, {'code': 'E3'}),
    (UpdateCategoryRequest, {'sensitive': False}),
    (CreateBuildingRequest, {'code': ' ', 'nameKo': '건물', 'nameEn': 'Building'}),
    (CreateCategoryRequest, {'nameKo': '지갑', 'nameEn': 'Wallet', 'sensitive': 1}),
    (UpdateCollectionRestrictionRequest, {'restricted': True}),
    (UpdateCollectionRestrictionRequest, {'restricted': False, 'disputeId': None}),
    (UpdateCollectionRestrictionRequest, {'restricted': 'false'}),
])
def test_invalid_requests(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_release_without_dispute_and_kst_page_serialization():
    assert UpdateCollectionRestrictionRequest.model_validate({'restricted': False}).dispute_id is None
    result = Page[StatisticsResponse](items=[StatisticsResponse(posted_count=0, collected_count=0,
        expired_count=0, as_of=datetime(2026, 11, 3, tzinfo=timezone.utc))],
        page=0, size=20, total_elements=1, total_pages=1).model_dump(mode='json')
    assert result['items'][0]['asOf'] == '2026-11-03T09:00:00+09:00'


@pytest.mark.parametrize('metadata', [{'email': 'secret@example.com'}, {'restricted': 1},
    {'fromRole': 'ROOT'}, {'decision': 'UNKNOWN'}, {'disputeId': 'bad'}, {'toStatus': 'OPEN'}])
def test_audit_rejects_unknown_or_invalid_metadata(metadata):
    with pytest.raises(ValueError):
        append_audit(None, None, 'ITEM_STATUS_CHANGED', 'FOUND_ITEM', uuid4(),
                     datetime.now(timezone.utc), **metadata)


def test_audit_calendar_year_handles_leap_day():
    assert one_year_after(datetime(2024, 2, 29, tzinfo=timezone.utc)) == datetime(2025, 2, 28, tzinfo=timezone.utc)


def test_openapi_documents_admin_contracts():
    paths = app.openapi()['paths']
    assert '201' in paths['/api/v1/admin/buildings']['post']['responses']
    assert '501' not in paths['/api/v1/admin/users']['get']['responses']
    params = {p['name'] for p in paths['/api/v1/admin/audit-logs']['get']['parameters']}
    assert {'from', 'to', 'actorId', 'targetId', 'action', 'page', 'size'} <= params
