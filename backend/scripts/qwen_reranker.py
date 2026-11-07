"""Instruction-aware Qwen reranking using next-token yes/no logit differences."""
import math
import time

from scripts.embedding_benchmark import normalize_text


PREFIX = (
    '<|im_start|>system\n'
    'Judge whether the Document meets the requirements based on the Query and the Instruct provided. '
    'Note that the answer can only be "yes" or "no".<|im_end|>\n'
    '<|im_start|>user\n'
)
SUFFIX = '<|im_end|>\n<|im_start|>assistant\n<think>\n\n</think>\n\n'


def prepare_inputs(tokenizer, instruction, inputs, pairs, max_length):
    prefix = tokenizer.encode(PREFIX, add_special_tokens=False)
    suffix = tokenizer.encode(SUFFIX, add_special_tokens=False)
    texts = [
        f'<Instruct>: {instruction}\n<Query>: {query}\n<Document>: {document}'
        for query, document in inputs
    ]
    body = tokenizer(texts, add_special_tokens=False, truncation=False, padding=False)
    ids = [prefix + tokens + suffix for tokens in body['input_ids']]
    for pair, tokens in zip(pairs, ids):
        if len(tokens) > max_length:
            raise ValueError(
                f"Pair exceeds max_length={max_length}: {pair['query']} / {pair['document']}"
            )
    return tokenizer.pad({'input_ids': ids}, padding=True, return_tensors='pt'), max(map(len, ids))


def answer_token_ids(tokenizer):
    ids = [tokenizer.encode(answer, add_special_tokens=False) for answer in ('no', 'yes')]
    if any(len(tokens) != 1 for tokens in ids) or ids[0] == ids[1]:
        raise ValueError('Qwen reranker requires distinct single-token no/yes answers')
    return ids[0][0], ids[1][0]


def rerank(model, rows, pairs, *, batch_size, device, cache_folder, local_files_only):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    instruction = model.get('instruction')
    max_length = model.get('max_length', 512)
    if not isinstance(instruction, str) or not instruction.strip():
        raise ValueError('Qwen requires a nonempty instruction')
    if isinstance(max_length, bool) or not isinstance(max_length, int) or max_length < 1:
        raise ValueError('max_length must be a positive integer')
    common = {
        'revision': model.get('revision'), 'cache_dir': cache_folder,
        'local_files_only': local_files_only, 'trust_remote_code': False,
    }
    started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(model['model'], padding_side='left', **common)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    no_id, yes_id = answer_token_ids(tokenizer)
    encoder = AutoModelForCausalLM.from_pretrained(
        model['model'], dtype=torch.float32, **common,
    ).to(device).eval()
    if max_length > encoder.config.max_position_embeddings:
        raise ValueError('max_length exceeds the model context limit')
    load_seconds = time.perf_counter() - started
    descriptions = {row['id']: normalize_text(row['text']) for row in rows}
    scored = []
    max_tokens = 0
    started = time.perf_counter()
    with torch.inference_mode():
        for offset in range(0, len(pairs), batch_size):
            batch = pairs[offset:offset + batch_size]
            inputs = [(descriptions[p['query']], descriptions[p['document']]) for p in batch]
            encoded, length = prepare_inputs(tokenizer, instruction, inputs, batch, max_length)
            max_tokens = max(max_tokens, length)
            encoded = {key: value.to(device) for key, value in encoded.items()}
            # Left padding puts every answer position last. Keep only final-position logits.
            logits = encoder(**encoded, use_cache=False, logits_to_keep=1).logits[:, -1, :]
            scores = (logits[:, yes_id].float() - logits[:, no_id].float()).cpu().tolist()
            if len(scores) != len(batch) or not all(math.isfinite(score) for score in scores):
                raise ValueError('Expected one finite yes/no logit difference per pair')
            scored.extend({**pair, 'score': score} for pair, score in zip(batch, scores))
            print(f"  scored {len(scored)}/{len(pairs)} pairs", flush=True)

    seconds = time.perf_counter() - started
    return scored, {
        'load_seconds': load_seconds, 'score_seconds': seconds,
        'pairs_per_second': len(pairs) / seconds if seconds else None,
        'device': str(encoder.device), 'dtype': str(encoder.dtype),
        'max_length': max_length, 'max_pair_tokens': max_tokens,
        'score_type': 'yes_logit_minus_no_logit; not a calibrated probability',
        'prompt_format': 'qwen3-reranker-official-prefix-suffix-v1',
    }
