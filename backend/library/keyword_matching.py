"""Exact and WordNet keyword evidence, independent of DB candidate lifecycle."""
from library.text_analysis_types import AnalysisError, AnalysisResult


def common_keywords(left: AnalysisResult, right: AnalysisResult) -> tuple[str, ...]:
    if left.profile_fingerprint != right.profile_fingerprint:
        raise AnalysisError('KEYWORD_PROFILE_MISMATCH')
    return tuple(sorted(set(left.keywords) & set(right.keywords)))
