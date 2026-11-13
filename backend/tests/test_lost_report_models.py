"""Lost report input boundaries and private response separation."""

from uuid import uuid4

import pytest
from pydantic import ValidationError

from schema.lost_reports import CreateLostReportRequest, LostReportSummary
from schema.lost_report_params import LostReportParams


@pytest.fixture
def body():
    return {
        'categoryId': str(uuid4()), 'description': ' wallet ',
        'possibleBuildingIds': [str(uuid4())],
        'lostDateFrom': '2026-11-01', 'lostDateTo': '2026-11-02',
        'privateIdentifyingDetails': ' secret ',
    }


@pytest.mark.parametrize('patch', [
    {'description': 'x' * 2001}, {'privateIdentifyingDetails': 'x' * 1001},
    {'description': True}, {'lostDateFrom': 0}, {'lostDateTo': None},
    {'lostDateFrom': '2026-11-01T00:00:00'}, {'possibleBuildingIds': [str(uuid4())] * 2},
    {'possibleBuildingIds': [str(uuid4()) for _ in range(101)]}, {'ownerId': str(uuid4())},
])
def test_invalid_input(body, patch):
    with pytest.raises(ValidationError):
        CreateLostReportRequest.model_validate({**body, **patch})


def test_all_fields_required_and_trimmed(body):
    for field in body:
        with pytest.raises(ValidationError):
            CreateLostReportRequest.model_validate({key: value for key, value in body.items() if key != field})
    request = CreateLostReportRequest.model_validate(body)
    assert request.description == 'wallet' and request.private_identifying_details == 'secret'
    assert 'private_identifying_details' not in LostReportSummary.model_fields
    assert LostReportParams().size == 20
