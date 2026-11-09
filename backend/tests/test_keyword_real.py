"""Explicit real-model checks of all-word subscription features."""

import os

import pytest

from library.keyword_subscription_matching import all_terms_match, atomic_terms
from library.text_analysis_types import AnalysisInput
from library.translation_runtime import TranslationRuntime, TranslationSettings


@pytest.mark.skipif(os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true',
                    reason='Set RUN_REAL_TEXT_ANALYSIS_TESTS=true with prepared model assets')
@pytest.mark.asyncio
async def test_real_keyword_all_words():
    runtime = TranslationRuntime(TranslationSettings.from_environment())
    try:
        await runtime.start()
        results = {}
        for value in ['black wallet', 'black bag', 'black coin wallet', '검은 지갑', '검은 가방', '검은 동전 지갑']:
            results[value] = await runtime.analyze(AnalysisInput(description=value))
        required = atomic_terms(results['black wallet'].keywords)
        assert required == ('lemma:black', 'lemma:wallet')
        assert not all_terms_match(required, results['black bag'].keywords)
        assert all_terms_match(required, results['black coin wallet'].keywords)
        # Verify the Korean examples end to end rather than assuming translation output.
        required_ko = atomic_terms(results['검은 지갑'].keywords)
        assert required_ko
        assert not all_terms_match(required_ko, results['검은 가방'].keywords)
        assert all_terms_match(required_ko, results['검은 동전 지갑'].keywords)
    finally:
        await runtime.close()
