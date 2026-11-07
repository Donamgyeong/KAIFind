import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.embedding_benchmark import score_pairs, select_threshold
from scripts.reranker_benchmark import build_pairs, main, query_metrics, rerank, run


DATASET = Path(__file__).resolve().parents[1] / 'experiments/embedding/descriptions.json'


def test_pairs_match_embedding_experiment_without_cross_split_pairs():
    rows = json.loads(DATASET.read_text())
    pairs = build_pairs(rows)
    vectors = {row['id']: [1.0] for row in rows}
    assert len(pairs) == 1664
    for split in ('calibration', 'evaluation'):
        selected = [p for p in pairs if p['split'] == split]
        expected = score_pairs([r for r in rows if r['split'] == split], vectors)
        assert [(p['query'], p['document'], p['label']) for p in selected] == [
            (p['query'], p['document'], p['label']) for p in expected
        ]
        assert sum(p['label'] for p in selected) == 192
        assert len(selected) == 832


def test_raw_logits_threshold_has_reject_all_boundary_above_observed_max():
    threshold, sweep = select_threshold([
        {'label': True, 'score': 12.0}, {'label': False, 'score': 8.0},
    ], 0.95)
    assert threshold == 12.0
    assert sweep[-1]['threshold'] > 12.0
    assert sweep[-1]['tp'] == sweep[-1]['fp'] == 0


def test_query_metrics_distinguishes_pair_and_query_false_positives_and_ties():
    pairs = [
        {'query': 'present', 'label': True, 'score': 5.0},
        {'query': 'present', 'label': False, 'score': 5.0},
        {'query': 'absent', 'label': False, 'score': 7.0},
        {'query': 'absent', 'label': False, 'score': 6.0},
    ]
    result = query_metrics(pairs, 6.0)
    assert result['top1_correct'] == 0
    assert result['unmatched_queries_accepted'] == 1
    assert result['unmatched_query_false_positive_rate'] == 1
    assert query_metrics(pairs, None)['unmatched_queries_accepted'] is None


def fixture_inputs():
    return (
        [{'id': 'q', 'text': ' 파란  컵 '}, {'id': 'd', 'text': 'blue cup'}],
        [{'query': 'q', 'document': 'd', 'label': True}],
    )


def test_cross_encoder_joint_input_revision_and_identity_activation():
    rows, pairs = fixture_inputs()
    encoder = MagicMock(device='cpu')
    encoder.model.config.num_labels = 1
    encoder.tokenizer.return_value = {'input_ids': [[1, 2, 3]]}
    encoder.predict.return_value.tolist.return_value = [8.5]
    with patch('sentence_transformers.CrossEncoder', return_value=encoder) as loader:
        scored, timing = rerank(
            {'model': 'fixture', 'revision': 'fixed', 'max_length': 128}, rows, pairs,
            batch_size=8, device='cpu', cache_folder='/tmp/cache', local_files_only=True,
        )
    assert loader.call_args.kwargs['revision'] == 'fixed'
    assert loader.call_args.kwargs['trust_remote_code'] is False
    assert loader.call_args.kwargs['local_files_only'] is True
    assert type(loader.call_args.kwargs['activation_fn']).__name__ == 'Identity'
    encoder.tokenizer.assert_called_once_with(
        ['파란 컵'], ['blue cup'], truncation=False, padding=False,
    )
    assert encoder.predict.call_args.args[0] == [('파란 컵', 'blue cup')]
    assert type(encoder.predict.call_args.kwargs['activation_fn']).__name__ == 'Identity'
    assert scored[0]['score'] == 8.5
    assert timing['max_pair_tokens'] == 3


@pytest.mark.parametrize('scores', [[float('nan')], [[1, 2]], [], [True]])
def test_invalid_prediction_is_rejected(scores):
    rows, pairs = fixture_inputs()
    encoder = MagicMock()
    encoder.model.config.num_labels = 1
    encoder.tokenizer.return_value = {'input_ids': [[1, 2]]}
    encoder.predict.return_value.tolist.return_value = scores
    with patch('sentence_transformers.CrossEncoder', return_value=encoder):
        with pytest.raises(ValueError, match='finite scalar'):
            rerank({'model': 'fixture'}, rows, pairs, batch_size=1, device='cpu',
                   cache_folder=None, local_files_only=True)


def test_pair_length_limit_rejects_before_truncation():
    rows, pairs = fixture_inputs()
    encoder = MagicMock()
    encoder.model.config.num_labels = 1
    encoder.tokenizer.return_value = {'input_ids': [[1, 2, 3]]}
    with patch('sentence_transformers.CrossEncoder', return_value=encoder):
        with pytest.raises(ValueError, match='q / d'):
            rerank({'model': 'fixture', 'max_length': 2}, rows, pairs, batch_size=1,
                   device='cpu', cache_folder=None, local_files_only=True)
    encoder.predict.assert_not_called()


def test_cli_default_files_exist_from_any_working_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with patch('scripts.reranker_benchmark.run') as runner:
        main([])
    args = runner.call_args.args[0]
    assert Path(args.dataset).is_file()
    assert Path(args.models).is_file()
    assert Path(args.models).name == 'rerankers.json'


def test_unmet_precision_does_not_choose_threshold_on_evaluation(tmp_path):
    config = tmp_path / 'models.json'
    config.write_text(json.dumps([{'name': 'fixture', 'model': 'fixture'}]))
    output = tmp_path / 'report.json'

    def fake_rerank(model, rows, pairs, **kwargs):
        return [{**p, 'score': 0.0 if p['label'] else 10.0} for p in pairs], {}

    with patch('scripts.reranker_benchmark.rerank', side_effect=fake_rerank):
        run(Namespace(
            dataset=str(DATASET), models=str(config), output=str(output),
            min_precision=0.95, batch_size=8, device='cpu', cache_folder=None,
            local_files_only=True,
        ))
    result = json.loads(output.read_text())['results'][0]
    assert result['threshold'] is None
    assert result['evaluation'] is None
    assert result['threshold_status'] == 'precision_target_unmet'
    assert result['query_metrics']['evaluation']['top1_correct'] == 0


def test_real_local_cross_encoder_generates_report_without_downloads(tmp_path):
    from transformers import BertConfig, BertForSequenceClassification, BertTokenizerFast

    model_path = tmp_path / 'tiny-reranker'
    model_path.mkdir()
    (model_path / 'vocab.txt').write_text(
        '[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nblue\ncup\n'
    )
    vocabulary = {
        token: index for index, token in enumerate((model_path / 'vocab.txt').read_text().splitlines())
    }
    BertTokenizerFast(vocab=vocabulary).save_pretrained(model_path)
    BertForSequenceClassification(BertConfig(
        vocab_size=7, hidden_size=16, num_hidden_layers=1, num_attention_heads=2,
        intermediate_size=32, max_position_embeddings=256, num_labels=1,
    )).save_pretrained(model_path)
    config = tmp_path / 'models.json'
    config.write_text(json.dumps([{
        'name': 'random-fixture', 'model': str(model_path), 'max_length': 256,
    }]))
    output = tmp_path / 'report.json'
    run(Namespace(
        dataset=str(DATASET), models=str(config), output=str(output),
        min_precision=0.95, batch_size=128, device='cpu', cache_folder=None,
        local_files_only=True,
    ))
    report = json.loads(output.read_text())
    result = report['results'][0]
    assert report['experiment'] == 'cross_encoder_all_eligible_pairs'
    assert result['score_seconds'] > 0
    assert len(result['pairs']['evaluation']) == 832
    assert result['query_metrics']['evaluation']['unmatched_queries'] == 16
    assert result['query_metrics']['evaluation']['matched_queries'] == 192
