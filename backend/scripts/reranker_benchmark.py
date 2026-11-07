"""Evaluate all eligible description pairs using a local CrossEncoder."""
import argparse
import hashlib
import json
import math
import time
from importlib.metadata import version
from pathlib import Path

from scripts.embedding_benchmark import (
    EXPERIMENT_DIR, metrics, normalize_text, select_threshold, validate_dataset,
)


def build_pairs(rows):
    pairs = []
    for query in rows:
        if query['role'] != 'query':
            continue
        for document in rows:
            if (
                document['role'] != 'document'
                or query['split'] != document['split']
                or query['category'] != document['category']
            ):
                continue
            pairs.append({
                'split': query['split'],
                'query': query['id'], 'document': document['id'],
                'category': query['category'],
                'scenario': query.get('scenario', 'unspecified'),
                'language': f"{query['language']}-{document['language']}",
                'label': query['item'] == document['item'],
            })

    for split in ('calibration', 'evaluation'):
        selected = [p for p in pairs if p['split'] == split]
        if not any(p['label'] for p in selected) or not any(not p['label'] for p in selected):
            raise ValueError(f'{split} needs positive and negative pairs')
    queries = {p['query'] for p in pairs}
    if any(row['role'] == 'query' and row['id'] not in queries for row in rows):
        raise ValueError('Every query needs at least one eligible document')
    return pairs


def rerank(model, rows, pairs, *, batch_size, device, cache_folder, local_files_only):
    backend = model.get('backend', 'cross_encoder')
    if backend == 'qwen_causal_lm':
        from scripts.qwen_reranker import rerank as rerank_qwen

        return rerank_qwen(
            model, rows, pairs, batch_size=batch_size, device=device,
            cache_folder=cache_folder, local_files_only=local_files_only,
        )
    if backend != 'cross_encoder':
        raise ValueError(f'Unsupported reranker backend: {backend}')

    from sentence_transformers import CrossEncoder
    from torch.nn import Identity

    max_length = model.get('max_length', 512)
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
        raise ValueError('max_length must be a positive integer')
    started = time.perf_counter()
    encoder = CrossEncoder(
        model['model'], revision=model.get('revision'), device=device,
        cache_folder=cache_folder, local_files_only=local_files_only,
        trust_remote_code=False, max_length=max_length, activation_fn=Identity(),
    )
    if encoder.model.config.num_labels != 1:
        raise ValueError('Reranker must have exactly one output logit')
    load_seconds = time.perf_counter() - started
    descriptions = {row['id']: normalize_text(row['text']) for row in rows}
    scored = []
    max_tokens = 0
    started = time.perf_counter()
    for offset in range(0, len(pairs), batch_size):
        batch = pairs[offset:offset + batch_size]
        inputs = [
            (model.get('query_prefix', '') + descriptions[p['query']],
             model.get('document_prefix', '') + descriptions[p['document']])
            for p in batch
        ]
        token_ids = encoder.tokenizer(
            [q for q, _ in inputs], [d for _, d in inputs],
            truncation=False, padding=False,
        )['input_ids']
        for pair, ids in zip(batch, token_ids):
            max_tokens = max(max_tokens, len(ids))
            if len(ids) > max_length:
                raise ValueError(
                    f"Pair exceeds max_length={max_length}: {pair['query']} / {pair['document']}"
                )

        scores = encoder.predict(
            inputs, batch_size=batch_size, show_progress_bar=False,
            activation_fn=Identity(), apply_softmax=False, convert_to_numpy=True,
        ).tolist()
        if len(scores) != len(batch) or any(
            isinstance(score, bool) or not isinstance(score, (int, float))
            or not math.isfinite(score) for score in scores
        ):
            raise ValueError('Expected one finite scalar logit per pair')
        scored.extend({**pair, 'score': score} for pair, score in zip(batch, scores))
        print(f"  scored {len(scored)}/{len(pairs)} pairs", flush=True)

    score_seconds = time.perf_counter() - started
    return scored, {
        'load_seconds': load_seconds, 'score_seconds': score_seconds,
        'pairs_per_second': len(pairs) / score_seconds if score_seconds else None,
        'device': str(encoder.device), 'max_length': max_length,
        'max_pair_tokens': max_tokens,
    }


def query_metrics(pairs, threshold):
    groups = {}
    for pair in pairs:
        groups.setdefault(pair['query'], []).append(pair)
    matched = [group for group in groups.values() if any(p['label'] for p in group)]
    absent = [group for group in groups.values() if not any(p['label'] for p in group)]
    # Count a tie between a correct and incorrect document as a failed top-1.
    correct = sum(
        max(p['score'] for p in group if p['label'])
        > max((p['score'] for p in group if not p['label']), default=-math.inf)
        for group in matched
    )
    accepted_absent = sum(
        any(p['score'] >= threshold for p in group) for group in absent
    ) if threshold is not None else None
    return {
        'matched_queries': len(matched), 'top1_correct': correct,
        'top1_accuracy': correct / len(matched) if matched else None,
        'unmatched_queries': len(absent),
        'unmatched_queries_accepted': accepted_absent,
        'unmatched_query_false_positive_rate': (
            accepted_absent / len(absent) if absent and threshold is not None else None
        ),
    }


def run(args):
    if not 0 <= args.min_precision <= 1 or args.batch_size < 1:
        raise ValueError('Invalid precision or batch size')
    raw = Path(args.dataset).read_bytes()
    rows = json.loads(raw)
    validate_dataset(rows)
    pairs = build_pairs(rows)
    models = json.loads(Path(args.models).read_text())
    if not models:
        raise ValueError('At least one reranker model is required')
    output = Path(args.output)
    if not output.parent.is_dir():
        raise ValueError(f'Output directory does not exist: {output.parent}')
    results = []
    for model in models:
        print(f"Evaluating {model['name']}: {len(pairs)} pairs", flush=True)
        scored, timing = rerank(
            model, rows, pairs, batch_size=args.batch_size, device=args.device,
            cache_folder=args.cache_folder, local_files_only=args.local_files_only,
        )
        splits = {
            split: [p for p in scored if p['split'] == split]
            for split in ('calibration', 'evaluation')
        }
        threshold, sweep = select_threshold(splits['calibration'], args.min_precision)
        evaluation = splits['evaluation']
        result = {
            'model': model, **timing, 'threshold': threshold,
            'threshold_status': 'selected' if threshold is not None else 'precision_target_unmet',
            'calibration_sweep': sweep,
            'calibration': metrics(splits['calibration'], threshold) if threshold is not None else None,
            'evaluation': metrics(evaluation, threshold) if threshold is not None else None,
            'query_metrics': {
                split: query_metrics(selected, threshold) for split, selected in splits.items()
            },
            'pairs': splits,
        }
        for field in ('language', 'scenario', 'category'):
            result[f'evaluation_by_{field}'] = {
                value: metrics([p for p in evaluation if p[field] == value], threshold)
                for value in sorted({p[field] for p in evaluation})
            } if threshold is not None else {}
        results.append(result)

    report = {
        'experiment': 'cross_encoder_all_eligible_pairs',
        'dataset_sha256': hashlib.sha256(raw).hexdigest(),
        'library_versions': {
            package: version(package)
            for package in ('sentence-transformers', 'torch', 'transformers')
        },
        'preprocessing': 'NFC + whitespace collapse v1',
        'score_type': 'raw_logit_or_yes_no_logit_difference; not a calibrated probability',
        'selection': 'calibration max F1 subject to minimum precision',
        'decision': 'score >= threshold', 'min_precision': args.min_precision,
        'results': results,
    }
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    print(f'Report: {output}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default=str(EXPERIMENT_DIR / 'descriptions.json'))
    parser.add_argument('--models', default=str(EXPERIMENT_DIR / 'rerankers.json'))
    parser.add_argument('--output', default='/tmp/reranker-report-v2.json')
    parser.add_argument('--min-precision', type=float, default=0.95)
    parser.add_argument('--batch-size', type=int, default=8)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--cache-folder', default=None)
    parser.add_argument('--local-files-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        run(args)
    except FileNotFoundError as error:
        parser.exit(1, f'Benchmark failed: file or directory not found: {error.filename}\n')
    except ValueError as error:
        parser.exit(1, f'Benchmark failed: {error}\n')
    except Exception as error:
        parser.exit(1, f'Benchmark failed ({type(error).__name__}); check model/revision/cache/device.\n')


if __name__ == '__main__':
    main()
