"""Opt-in actual Korean translation -> canonical analysis -> matching candidate."""
import os

import pytest
from sqlalchemy import select

from library.translation_runtime import TranslationRuntime, TranslationSettings
from model import FoundItem, LostReport, MatchCandidate
from test_analysis_worker import analysis_env, worker as analysis_worker
from test_matching_service import setup, drain, page


@pytest.mark.asyncio
@pytest.mark.skipif(os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true', reason='Real model opt-in')
async def test_real_korean_analysis_to_keyword_candidate(analysis_env):
    env = analysis_env
    runtime = TranslationRuntime(TranslationSettings.from_environment())
    try:
        await runtime.start()
        env.runtime = runtime
        async with env.factory() as db, db.begin():
            item = await db.get(FoundItem, env.ids['item'])
            item.title = 'Wallet'
            item.description = '검은 지갑입니다.'
            report = await db.get(LostReport, env.ids['report'])
            report.description = '검은 지갑입니다.'
        await setup(env, building=False, ready=False)
        while await analysis_worker(env).run_once():
            pass
        await drain(env)
        result = await page(env)
        assert result.is_complete and result.total_elements == 1
        assert result.items[0].matched_by == ['KEYWORD']
        async with env.factory() as db:
            candidate = await db.scalar(select(MatchCandidate))
            assert 'lemma:wallet' in candidate.common_keywords
    finally:
        await runtime.close()
