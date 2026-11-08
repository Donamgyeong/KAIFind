"""Explicit offline integration checks with the fixed real model, never the DB."""
import asyncio
from dataclasses import replace
import json
import os
import threading
import time

import pytest

from library.text_analysis_types import AnalysisError, AnalysisInput
from library.translation_runtime import TranslationRuntime, TranslationSettings


@pytest.mark.skipif(os.getenv('RUN_REAL_TEXT_ANALYSIS_TESTS') != 'true',
                    reason='Set RUN_REAL_TEXT_ANALYSIS_TESTS=true after preparing model assets')
def test_real_resident_model_offline_and_token_boundaries(monkeypatch):
    monkeypatch.setenv('HF_HUB_OFFLINE', '1')
    monkeypatch.setenv('TRANSFORMERS_OFFLINE', '1')

    async def run():
        runtime = TranslationRuntime(TranslationSettings.from_environment())
        try:
            await runtime.start()
            assert runtime.ready and runtime.load_count == 1
            assert runtime.thread_id != threading.get_ident()
            profile = runtime.profile
            assert profile['runtime_config']['dtype'] == 'float32'
            assert len(profile['fingerprint']) == 64
            for foreign in ('黒い財布です。', '黑色钱包', 'محفظة سوداء', 'portefeuille noir'):
                value = AnalysisInput(description=foreign)
                result = await runtime.analyze(value)
                assert result.source_language == 'EN'
                assert json.loads(result.translated_text)['description'] == foreign
                assert result.keywords
            value = AnalysisInput(description='검은 지갑입니다.', title='Sony WH-1000XM5')
            result = await runtime.analyze(value)
            assert result == await runtime.analyze(value)
            assert result.source_language == 'MIXED'
            assert 'identifier:wh1000xm5' in result.keywords
            assert json.loads(result.translated_text)['title'] == value.title
            assert runtime.load_count == 1

            # Exercise the real tokenizer with a controlled generator, checking
            # all input tokens reach generation without exceeding model limits.
            def check_limits():
                import torch
                original_generate = runtime._model.generate
                original_settings = runtime.settings
                captured = []
                output_ids = runtime._tokenizer.encode('wallet', add_special_tokens=False)
                output = torch.tensor([[runtime._tokenizer.pad_token_id, *output_ids,
                                        runtime._tokenizer.eos_token_id]])
                def record(**kwargs):
                    ids = kwargs['input_ids']
                    assert ids.ndim == 2 and ids.shape[1] <= runtime.settings.input_tokens
                    captured.extend(ids[0].tolist()[:-1])
                    return output
                runtime._model.generate = record
                try:
                    long_text = '검은지갑' * 300
                    expected = runtime._tokenizer.encode(long_text, add_special_tokens=False)
                    runtime._translate(long_text, time.monotonic() + 10)
                    assert captured == expected and len(expected) > 256
                    runtime.settings = replace(original_settings, max_chunks=1)
                    with pytest.raises(AnalysisError, match='TEXT_CHUNK_LIMIT'):
                        runtime._translate(long_text, time.monotonic() + 10)
                    runtime.settings = original_settings
                    runtime._model.generate = lambda **kwargs: torch.tensor([[32000, 10]])
                    with pytest.raises(AnalysisError, match='TRANSLATION_OUTPUT_LIMIT'):
                        runtime._translate('검은 지갑', time.monotonic() + 10)
                finally:
                    runtime._model.generate = original_generate
                    runtime.settings = original_settings
            await asyncio.get_running_loop().run_in_executor(runtime._executor, check_limits)
        finally:
            assert await runtime.close()
            assert await runtime.close()
        assert not runtime.ready
    asyncio.run(run())
