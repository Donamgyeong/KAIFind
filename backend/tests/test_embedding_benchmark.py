import json
from importlib.metadata import version
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.embedding_benchmark import (
    embed, main, metrics, score_pairs, select_threshold, unit_vector, validate_dataset,
)


def test_cli_defaults_exist_independently_of_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch('scripts.embedding_benchmark.run') as runner:
        main([])

    args = runner.call_args.args[0]
    assert Path(args.dataset).is_absolute()
    assert Path(args.dataset).is_file()
    assert Path(args.models).is_absolute()
    assert Path(args.models).is_file()
    assert Path(args.models).name == 'models.json'


def test_cli_missing_file_shows_path(tmp_path, capsys):
    missing = tmp_path / 'missing-models.json'
    with pytest.raises(SystemExit) as error:
        main(['--models', str(missing)])

    assert error.value.code == 1
    assert str(missing) in capsys.readouterr().err


def test_threshold_is_selected_on_calibration_only_and_includes_boundary():
    calibration = [{'label': True, 'score': 0.8}, {'label': False, 'score': 0.7}]
    threshold, _ = select_threshold(calibration, 0.95)
    assert threshold == 0.8
    assert metrics(calibration, threshold)['tp'] == 1
    evaluation = [{'label': False, 'score': 0.9}, {'label': True, 'score': 0.6}]
    assert metrics(evaluation, threshold)['fp'] == 1
    assert metrics(evaluation, threshold)['fn'] == 1
    assert select_threshold([{'label': True, 'score': 0.5},
                             {'label': False, 'score': 0.5}], 0.95)[0] is None


@pytest.mark.parametrize('vector', [[], [0, 0], [float('nan')], [float('inf')], [True]])
def test_invalid_vectors_are_rejected(vector):
    with pytest.raises(ValueError):
        unit_vector(vector)


def test_dataset_and_cosine_scoring():
    rows = json.loads(Path('experiments/embedding/descriptions.json').read_text())
    validate_dataset(rows)
    items = sorted({row['item'] for row in rows})
    vectors = {row['id']: [int(item == row['item']) for item in items] for row in rows}
    for split in ('calibration', 'evaluation'):
        pairs = score_pairs([r for r in rows if r['split'] == split], vectors)
        assert len(pairs) == 832
        assert sum(p['label'] for p in pairs) == 192
        absent_pairs = [p for p in pairs if p['scenario'] == 'no_match']
        assert len(absent_pairs) == 64
        assert not any(p['label'] for p in absent_pairs)
        assert metrics(pairs, 1.0)['f1'] == 1
    rows[-1]['item'] = rows[0]['item']
    with pytest.raises(ValueError, match='both splits'):
        validate_dataset(rows)


def test_diverse_dataset_has_balanced_coverage_and_disjoint_items():
    rows = json.loads(Path('experiments/embedding/descriptions.json').read_text())
    split_items = {}
    split_texts = {}
    coverage = {}
    for split in ('calibration', 'evaluation'):
        selected = [r for r in rows if r['split'] == split]
        split_items[split] = {r['item'] for r in selected}
        split_texts[split] = {r['text'] for r in selected}
        documents = [r for r in selected if r['role'] == 'document']
        queries = [r for r in selected if r['role'] == 'query']
        coverage[split] = sorted(
            (r['category'], r['role'], r['language'], r['scenario'])
            for r in selected
        )
        assert len(documents) == 32
        assert len(queries) == 208
        assert len({r['category'] for r in selected}) == 8
        for category in {r['category'] for r in selected}:
            category_docs = [r for r in documents if r['category'] == category]
            assert len(category_docs) == 4
            assert [r['language'] for r in category_docs].count('ko') == 2
            assert [r['language'] for r in category_docs].count('en') == 2
        for query in queries:
            matches = [d for d in documents if d['item'] == query['item']]
            assert len(matches) == (0 if query['scenario'] == 'no_match' else 1)

    assert coverage['calibration'] == coverage['evaluation']
    assert not split_items['calibration'] & split_items['evaluation']
    assert not split_texts['calibration'] & split_texts['evaluation']


def test_dimension_mismatch_is_rejected():
    with pytest.raises(ValueError, match='dimensions'):
        score_pairs([], {'a': [1], 'b': [1, 2]})


def test_local_model_revision_prefixes_and_encode_options():
    model = {'model': 'fixture', 'revision': 'fixed-sha', 'query_prefix': 'query: '}
    rows = [{'id': 'q', 'role': 'query', 'text': '  파란  컵 '},
            {'id': 'd', 'role': 'document', 'text': 'blue cup'}]
    encoder = MagicMock(max_seq_length=128, device='cpu')
    encoder.tokenizer.return_value = {'input_ids': [[1, 2, 3], [1, 2]]}
    encoder.encode.return_value.tolist.return_value = [[1, 0], [0, 1]]

    with patch('sentence_transformers.SentenceTransformer', return_value=encoder) as loader:
        vectors, timing = embed(model, rows, 2, cache_folder='/tmp/models', local_files_only=True)
    loader.assert_called_once_with(
        'fixture', revision='fixed-sha', device='cpu', cache_folder='/tmp/models',
        local_files_only=True, trust_remote_code=False,
    )
    encoder.encode.assert_called_once_with(
        ['query: 파란 컵', 'blue cup'], batch_size=2, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True, prompt='',
    )
    assert vectors == {'q': [1, 0], 'd': [0, 1]}
    assert timing['max_input_tokens'] == 3
    assert timing['device'] == 'cpu'


def test_long_input_is_rejected_before_silent_truncation():
    encoder = MagicMock(max_seq_length=2)
    encoder.tokenizer.return_value = {'input_ids': [[1, 2, 3]]}
    with patch('sentence_transformers.SentenceTransformer', return_value=encoder):
        with pytest.raises(ValueError, match='max_seq_length=2'):
            embed({'model': 'fixture'}, [{'id': 'q', 'role': 'query', 'text': 'long'}], 1)
    encoder.encode.assert_not_called()


def test_saved_model_prompt_is_applied_once_and_counted_in_length_check():
    encoder = MagicMock(max_seq_length=128, device='cpu', default_prompt_name='query')
    encoder.prompts = {'query': 'Match product: '}
    encoder.tokenizer.return_value = {'input_ids': [[1, 2, 3, 4]]}
    encoder.encode.return_value.tolist.return_value = [[1, 0]]
    rows = [{'id': 'q', 'role': 'query', 'text': ' blue  cup '}]
    with patch('sentence_transformers.SentenceTransformer', return_value=encoder) as loader:
        _, timing = embed({
            'model': 'fixture', 'use_model_prompt': True, 'dtype': 'float32',
        }, rows, 1)

    assert loader.call_args.kwargs['model_kwargs'] == {'dtype': 'float32'}
    encoder.tokenizer.assert_called_once_with(
        ['Match product: blue cup'], truncation=False, padding=False,
    )
    assert encoder.encode.call_args.args[0] == ['blue cup']
    assert encoder.encode.call_args.kwargs['prompt'] == 'Match product: '
    assert timing['applied_prompt'] == 'Match product: '


def test_real_local_transformer_produces_benchmark_report(tmp_path):
    """Exercise actual libraries without downloads; random weights do not test quality."""
    from argparse import Namespace

    from sentence_transformers import SentenceTransformer, models
    from transformers import BertConfig, BertModel, BertTokenizerFast

    from scripts.embedding_benchmark import run

    base = tmp_path / 'bert'
    base.mkdir()
    (base / 'vocab.txt').write_text(
        '[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nblue\ncup\n'
    )
    vocabulary = {
        token: index for index, token in enumerate((base / 'vocab.txt').read_text().splitlines())
    }
    BertTokenizerFast(vocab=vocabulary).save_pretrained(base)
    BertModel(BertConfig(
        vocab_size=7, hidden_size=16, num_hidden_layers=1,
        num_attention_heads=2, intermediate_size=32, max_position_embeddings=128,
    )).save_pretrained(base)
    local_model = tmp_path / 'sentence-model'
    SentenceTransformer(modules=[
        models.Transformer(str(base), max_seq_length=128), models.Pooling(16),
    ]).save_pretrained(str(local_model))
    config = tmp_path / 'models.json'
    config.write_text(json.dumps([{'name': 'random-fixture', 'model': str(local_model)}]))
    output = tmp_path / 'report.json'

    run(Namespace(
        dataset='experiments/embedding/descriptions.json', models=str(config),
        output=str(output), min_precision=0.95, batch_size=16, device='cpu',
        cache_folder=None, local_files_only=True,
    ))

    report = json.loads(output.read_text())
    result = report['results'][0]
    assert result['dimensions'] == 16
    assert result['device'] == 'cpu'
    assert result['encode_seconds'] > 0
    assert len(result['pairs']['evaluation']) == 832
    if result['threshold'] is not None:
        assert 'no_match' in result['evaluation_by_scenario']
    assert report['library_versions']['sentence-transformers'] == version('sentence-transformers')
