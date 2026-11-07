"""Compare local SentenceTransformer models and calibrate cosine thresholds."""
import argparse
import hashlib
import json
import math
import time
import unicodedata
from importlib.metadata import version
from pathlib import Path


EXPERIMENT_DIR = Path(__file__).resolve().parents[1] / 'experiments' / 'embedding'


def normalize_text(text):
    return ' '.join(unicodedata.normalize('NFC', text).split())


def unit_vector(vector):
    if not vector or any(isinstance(x, bool) or not isinstance(x, (int, float))
                         or not math.isfinite(x) for x in vector):
        raise ValueError('Embedding must contain finite numbers')
    norm = math.hypot(*vector)
    if not math.isfinite(norm) or norm == 0:
        raise ValueError('Embedding norm must be finite and nonzero')
    return [x / norm for x in vector]


def score_pairs(rows, vectors):
    dimensions = {len(vector) for vector in vectors.values()}
    if len(dimensions) != 1:
        raise ValueError('Inconsistent embedding dimensions')
    normalized = {key: unit_vector(value) for key, value in vectors.items()}
    pairs = []
    for query in rows:
        if query['role'] != 'query':
            continue
        for document in rows:
            if document['role'] != 'document' or query['category'] != document['category']:
                continue
            score = max(-1.0, min(1.0, sum(
                a * b for a, b in zip(normalized[query['id']], normalized[document['id']])
            )))
            pairs.append({
                'query': query['id'], 'document': document['id'],
                'category': query['category'],
                'scenario': query.get('scenario', 'unspecified'),
                'language': f"{query['language']}-{document['language']}",
                'label': query['item'] == document['item'], 'score': score,
            })
    if not pairs or not any(p['label'] for p in pairs) or all(p['label'] for p in pairs):
        raise ValueError('Each split needs both positive and negative pairs')
    return pairs


def metrics(pairs, threshold):
    tp = sum(p['label'] and p['score'] >= threshold for p in pairs)
    fp = sum(not p['label'] and p['score'] >= threshold for p in pairs)
    fn = sum(p['label'] and p['score'] < threshold for p in pairs)
    tn = len(pairs) - tp - fp - fn
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        'tp': tp, 'fp': fp, 'fn': fn, 'tn': tn,
        'precision': precision, 'recall': recall,
        'f1': 2 * precision * recall / (precision + recall) if precision + recall else 0.0,
        'false_positive_rate': fp / (fp + tn) if fp + tn else None,
        'miss_rate': fn / (tp + fn) if tp + fn else None,
    }


def select_threshold(pairs, min_precision):
    # Include the reject-all boundary; equality always counts as a match.
    scores = {p['score'] for p in pairs}
    thresholds = sorted(scores | {math.nextafter(max(scores), math.inf)})
    sweep = [{'threshold': t, **metrics(pairs, t)} for t in thresholds]
    eligible = [r for r in sweep if r['precision'] >= min_precision and r['tp'] > 0]
    if not eligible:
        return None, sweep
    best = max(eligible, key=lambda r: (r['f1'], r['precision'], r['threshold']))
    return best['threshold'], sweep


def validate_dataset(rows):
    ids = set()
    item_splits = {}
    for row in rows:
        if row['id'] in ids:
            raise ValueError('Duplicate description ID')
        ids.add(row['id'])
        if row['split'] not in {'calibration', 'evaluation'}:
            raise ValueError('Unknown split')
        if row['role'] not in {'query', 'document'} or not normalize_text(row['text']):
            raise ValueError('Invalid role or empty description')
        previous = item_splits.setdefault(row['item'], row['split'])
        if previous != row['split']:
            raise ValueError('Same item appears in both splits')


def embed(
    model, rows, batch_size, *, device='cpu', cache_folder=None,
    local_files_only=False,
):
    from sentence_transformers import SentenceTransformer

    load_options = {}
    if model.get('dtype'):
        load_options['model_kwargs'] = {'dtype': model['dtype']}
    started = time.perf_counter()
    encoder = SentenceTransformer(
        model['model'],
        revision=model.get('revision'),
        device=device,
        cache_folder=cache_folder,
        local_files_only=local_files_only,
        trust_remote_code=False,
        **load_options,
    )
    load_seconds = time.perf_counter() - started
    prompt = ''
    if model.get('use_model_prompt', False):
        name = encoder.default_prompt_name
        if not name or name not in encoder.prompts:
            raise ValueError('Model does not define a default prompt')
        if model.get('query_prefix') or model.get('document_prefix'):
            raise ValueError('Model prompt cannot be combined with role prefixes')
        prompt = encoder.prompts[name]
    inputs = [model.get(row['role'] + '_prefix', '') + normalize_text(row['text'])
              for row in rows]
    lengths = [len(ids) for ids in encoder.tokenizer(
        [prompt + text for text in inputs], truncation=False, padding=False,
    )['input_ids']]
    too_long = [row['id'] for row, length in zip(rows, lengths)
                if length > encoder.max_seq_length]
    if too_long:
        raise ValueError(
            f"Inputs exceed max_seq_length={encoder.max_seq_length}: {too_long}"
        )

    started = time.perf_counter()
    embeddings = encoder.encode(
        inputs,
        batch_size=batch_size,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,
        prompt=prompt,
    ).tolist()
    encode_seconds = time.perf_counter() - started
    if len(embeddings) != len(rows):
        raise ValueError('Embedding count does not match descriptions')
    vectors = {row['id']: vector for row, vector in zip(rows, embeddings)}
    return vectors, {
        'load_seconds': load_seconds,
        'encode_seconds': encode_seconds,
        'descriptions_per_second': len(rows) / encode_seconds if encode_seconds else None,
        'device': str(encoder.device),
        'max_seq_length': encoder.max_seq_length,
        'max_input_tokens': max(lengths),
        'applied_prompt': prompt,
    }


def run(args):
    if not 0 <= args.min_precision <= 1 or args.batch_size < 1:
        raise ValueError('Invalid precision or batch size')
    raw = Path(args.dataset).read_bytes()
    rows = json.loads(raw)
    validate_dataset(rows)
    models = json.loads(Path(args.models).read_text())
    results = []
    for model in models:
        print(f"Evaluating {model['name']}", flush=True)
        vectors, timing = embed(
            model, rows, args.batch_size,
            device=args.device, cache_folder=args.cache_folder,
            local_files_only=args.local_files_only,
        )
        splits = {
            split: score_pairs([r for r in rows if r['split'] == split], vectors)
            for split in ('calibration', 'evaluation')
        }
        threshold, sweep = select_threshold(splits['calibration'], args.min_precision)
        evaluation = splits['evaluation']
        results.append({
            'model': model, 'dimensions': len(next(iter(vectors.values()))), **timing,
            'threshold': threshold, 'calibration_sweep': sweep,
            'evaluation': metrics(evaluation, threshold) if threshold is not None else None,
            'evaluation_by_language': {
                language: metrics([p for p in evaluation if p['language'] == language], threshold)
                for language in sorted({p['language'] for p in evaluation})
            } if threshold is not None else {},
            'evaluation_by_scenario': {
                scenario: metrics([p for p in evaluation if p['scenario'] == scenario], threshold)
                for scenario in sorted({p['scenario'] for p in evaluation})
            } if threshold is not None else {},
            'pairs': splits,
        })
    report = {
        'dataset_sha256': hashlib.sha256(raw).hexdigest(),
        'library_versions': {
            package: version(package)
            for package in ('sentence-transformers', 'torch', 'transformers')
        },
        'preprocessing': 'NFC + whitespace collapse v1', 'similarity': 'cosine >= threshold',
        'selection': 'calibration max F1 subject to minimum precision',
        'min_precision': args.min_precision, 'results': results,
    }
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'Report: {args.output}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', default=str(EXPERIMENT_DIR / 'descriptions.json'))
    parser.add_argument('--models', default=str(EXPERIMENT_DIR / 'models.json'))
    parser.add_argument('--output', default='/tmp/embedding-report.json')
    parser.add_argument('--min-precision', type=float, default=0.95)
    parser.add_argument('--batch-size', type=int, default=16)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--cache-folder', default=None)
    parser.add_argument('--local-files-only', action='store_true')
    args = parser.parse_args(argv)
    try:
        run(args)
    except Exception as error:
        if isinstance(error, FileNotFoundError):
            parser.exit(1, f'Benchmark failed: file or directory not found: {error.filename}\n')
        if isinstance(error, ValueError):
            parser.exit(1, f'Benchmark failed: {error}\n')
        parser.exit(1, f'Benchmark failed ({type(error).__name__}); check model/cache/device.\n')


if __name__ == '__main__':
    main()
