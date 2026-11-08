"""Language policy, deterministic extraction and runtime admission/lifecycle."""
import asyncio
import json
from pathlib import Path
import threading

import pytest

from library.text_analysis_types import AnalysisError, AnalysisInput, MODEL_ID, MODEL_REVISION
from library.text_input import source_language
from library.text_keywords import KeywordExtractor
from library.translation_runtime import REQUIRED_ASSETS, TranslationRuntime, TranslationSettings, verify_assets


@pytest.mark.parametrize('value,expected', [
    ('검은 지갑', 'KO'), ('검은 Sony 지갑', 'MIXED'), ('black wallet', 'EN'),
    ('黒い財布です。', 'EN'), ('黑色钱包', 'EN'), ('محفظة سوداء', 'EN'),
    ('portefeuille noir', 'EN'), ('123 !!!', 'EN'), ('가', 'KO'),
])
def test_non_hangul_inputs_are_assumed_english(value, expected):
    assert source_language(value) == expected


def test_input_hash_preserves_field_boundaries_and_normalization():
    left = AnalysisInput(description='bc', title='a')
    right = AnalysisInput(description='c', title='ab')
    assert left.source_hash != right.source_hash
    assert AnalysisInput(description=' ＡＢＣ ').source_hash == AnalysisInput(description='ABC').source_hash
    assert json.loads(left.canonical()) == {'description': 'bc', 'title': 'a'}


@pytest.mark.parametrize('values', [
    {'description': ''}, {'description': ' '}, {'description': 'x' * 2001},
    {'description': 'x', 'title': ''}, {'description': 'x', 'private_details': 'secret'},
])
def test_input_rejects_invalid_or_private_fields(values):
    with pytest.raises((AnalysisError, TypeError)):
        AnalysisInput(**values)


def test_extraction_matches_labeled_english_and_unsupported_samples():
    extractor = KeywordExtractor()
    samples = json.loads(Path('tests/data/text_analysis_samples.json').read_text())
    for sample in samples:
        if source_language(sample['description']) != 'EN':
            continue
        fields = [sample.get('title', ''), sample['description']]
        keywords, attributes = extractor.extract(fields, fields)
        assert set(sample['expected_keywords']) <= set(keywords), sample['name']
        assert not set(sample.get('forbidden_keywords', [])) & set(keywords), sample['name']
        assert list(keywords) == sorted(set(keywords))
        assert 'negated' in attributes


def test_source_identifiers_and_negated_terms_are_preserved_separately():
    keywords, attributes = KeywordExtractor().extract(
        ['Sony headphones without strap'], ['Sony WH-1000XM5 헤드폰'],
    )
    assert 'identifier:wh1000xm5' in keywords
    assert 'lemma:strap' not in keywords
    assert 'lemma:strap' in attributes['negated']
    assert not any('헤드폰' in keyword for keyword in keywords)


def test_corrupt_or_missing_local_model_is_an_explicit_failure(tmp_path):
    with pytest.raises(AnalysisError, match='MODEL_ASSETS_INVALID'):
        verify_assets(tmp_path)


def test_asset_manifest_detects_changed_and_unrecorded_files(tmp_path):
    import hashlib

    files = {}
    for name in REQUIRED_ASSETS:
        (tmp_path / name).write_bytes(b'synthetic-asset')
        files[name] = hashlib.sha256(b'synthetic-asset').hexdigest()
    (tmp_path / 'assets.json').write_text(json.dumps({
        'model_name': MODEL_ID, 'revision': MODEL_REVISION, 'files': files,
    }))
    assert verify_assets(tmp_path)['revision'] == MODEL_REVISION
    (tmp_path / 'tokenizer.json').write_text('{}')
    with pytest.raises(AnalysisError, match='MODEL_ASSETS_INVALID'):
        verify_assets(tmp_path)
    (tmp_path / 'tokenizer.json').unlink()
    (tmp_path / 'config.json').write_bytes(b'changed')
    with pytest.raises(AnalysisError, match='MODEL_ASSETS_INVALID'):
        verify_assets(tmp_path)


def test_runtime_cancellation_does_not_admit_another_inference():
    async def run():
        runtime = TranslationRuntime(TranslationSettings(timeout_seconds=.05))
        runtime.ready = True
        entered, release = threading.Event(), threading.Event()
        def slow(value):
            entered.set()
            release.wait(2)
            return 'done'
        runtime._analyze = slow
        try:
            task = asyncio.create_task(runtime.analyze(AnalysisInput(description='wallet')))
            await asyncio.to_thread(entered.wait, 1)
            with pytest.raises(AnalysisError, match='ANALYSIS_BUSY'):
                await runtime.analyze(AnalysisInput(description='bag'))
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(AnalysisError, match='ANALYSIS_BUSY'):
                await runtime.analyze(AnalysisInput(description='bag'))
        finally:
            release.set()
            await runtime.close()
    asyncio.run(run())


def test_runtime_timeout_keeps_actual_inference_tracked():
    async def run():
        runtime = TranslationRuntime(TranslationSettings(timeout_seconds=.01))
        runtime.ready = True
        release = threading.Event()
        runtime._analyze = lambda value: release.wait(2)
        try:
            with pytest.raises(AnalysisError, match='ANALYSIS_TIMEOUT'):
                await runtime.analyze(AnalysisInput(description='wallet'))
            with pytest.raises(AnalysisError, match='ANALYSIS_BUSY'):
                await runtime.analyze(AnalysisInput(description='wallet'))
        finally:
            release.set()
            assert await runtime.close()
    asyncio.run(run())


def test_loading_failure_closes_executor(tmp_path):
    async def run():
        runtime = TranslationRuntime(TranslationSettings(model_directory=tmp_path))
        with pytest.raises(AnalysisError, match='MODEL_ASSETS_INVALID'):
            await runtime.start()
        assert not runtime.ready and runtime._closed
        assert await runtime.close()
    asyncio.run(run())
