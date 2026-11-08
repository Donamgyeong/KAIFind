"""Progress and candidate DTO boundaries; no analysis or matching side effects."""
from copy import deepcopy
from uuid import uuid4

import pytest
from pydantic import ValidationError

from schema.matching import MatchCandidatePage, MatchingProgress, TextAnalysisProgress
from schema.matching_params import MatchingParams


def page_data():
    item, category, building, report, candidate = [str(uuid4()) for _ in range(5)]
    return {
        'analysisStatus': 'READY', 'matchingStatus': 'READY', 'isComplete': True,
        'items': [{
            'candidateId': candidate, 'reportId': report, 'itemId': item,
            'matchedAt': '2026-11-08T00:00:00Z', 'matchedBy': ['BUILDING', 'KEYWORD'],
            'item': {
                'itemId': item, 'categoryId': category, 'foundBuildingId': building,
                'title': 'Wallet', 'foundAt': '2026-11-07T00:00:00Z',
                'status': 'POSTED', 'sensitive': True,
            },
        }],
        'page': 0, 'size': 20, 'totalElements': 1, 'totalPages': 1,
    }


def test_aliases_kst_and_minimal_candidate_payload():
    result = MatchCandidatePage.model_validate(page_data()).model_dump(mode='json')
    assert result['items'][0]['matchedAt'] == '2026-11-08T09:00:00+09:00'
    assert result['items'][0]['item']['foundAt'].endswith('+09:00')
    assert set(result) == {'analysisStatus', 'matchingStatus', 'isComplete', 'items',
                           'page', 'size', 'totalElements', 'totalPages'}
    assert set(result['items'][0]['item']) == {
        'itemId', 'categoryId', 'foundBuildingId', 'title', 'foundAt', 'status', 'sensitive',
    }


@pytest.mark.parametrize('status', ['PENDING', 'PROCESSING', 'FAILED'])
def test_incomplete_empty_page_is_distinct_from_completed_no_matches(status):
    values = {**page_data(), 'matchingStatus': status, 'isComplete': False,
              'items': [], 'totalElements': 0, 'totalPages': 0}
    assert MatchCandidatePage.model_validate(values).is_complete is False
    with pytest.raises(ValidationError):
        MatchCandidatePage.model_validate({**values, 'isComplete': True})


@pytest.mark.parametrize('field,value', [
    ('analysisStatus', 'SUPERSEDED'), ('matchingStatus', 'UNKNOWN'),
    ('isComplete', 'true'), ('page', -1), ('size', 101), ('totalElements', -1),
])
def test_invalid_progress_and_pagination_are_rejected(field, value):
    with pytest.raises(ValidationError):
        MatchCandidatePage.model_validate({**page_data(), field: value})


def test_required_progress_is_not_defaulted_and_payload_does_not_leak_fields():
    with pytest.raises(ValidationError):
        TextAnalysisProgress.model_validate({})
    with pytest.raises(ValidationError):
        MatchingProgress.model_validate({'analysisStatus': 'PENDING'})
    for private_field in ('translatedText', 'keywords', 'privateIdentifyingDetails', 'url'):
        values = deepcopy(page_data())
        values['items'][0]['item'][private_field] = 'private'
        with pytest.raises(ValidationError):
            MatchCandidatePage.model_validate(values)
    values = page_data()
    values['items'][0]['matchedBy'] = ['BUILDING', 'BUILDING']
    with pytest.raises(ValidationError):
        MatchCandidatePage.model_validate(values)


def test_history_can_be_complete_without_reanalyzing_closed_report():
    values = {**page_data(), 'analysisStatus': 'FAILED'}
    assert MatchCandidatePage.model_validate(values).is_complete is True


def test_matching_query_defaults_bounds_and_unknown_fields():
    assert MatchingParams().model_dump() == {'page': 0, 'size': 20}
    assert MatchingParams.model_validate({'page': '1', 'size': '100'}).page == 1
    for values in ({'page': -1}, {'size': 0}, {'size': 101}, {'ownerId': str(uuid4())}):
        with pytest.raises(ValidationError):
            MatchingParams.model_validate(values)
