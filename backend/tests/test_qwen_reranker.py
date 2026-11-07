from unittest.mock import MagicMock, patch

import pytest

from scripts.qwen_reranker import PREFIX, SUFFIX, answer_token_ids, prepare_inputs, rerank
from scripts.reranker_benchmark import rerank as dispatch_rerank


def test_prompt_includes_instruction_and_preserves_official_prefix_suffix():
    tokenizer = MagicMock()
    tokenizer.encode.side_effect = [[10], [20]]
    tokenizer.return_value = {'input_ids': [[30, 31], [40]]}
    pairs = [{'query': 'q1', 'document': 'd1'}, {'query': 'q2', 'document': 'd2'}]
    _, length = prepare_inputs(
        tokenizer, 'Check explicit color conflicts.', [('white cup', 'red cup'), ('pen', 'pen')],
        pairs, 4,
    )
    assert tokenizer.encode.call_args_list[0].args == (PREFIX,)
    assert tokenizer.encode.call_args_list[1].args == (SUFFIX,)
    assert tokenizer.call_args.args[0][0] == (
        '<Instruct>: Check explicit color conflicts.\n<Query>: white cup\n<Document>: red cup'
    )
    assert tokenizer.call_args.kwargs['truncation'] is False
    assert tokenizer.pad.call_args.args[0]['input_ids'] == [[10, 30, 31, 20], [10, 40, 20]]
    assert length == 4


def test_length_check_counts_system_and_answer_suffix():
    tokenizer = MagicMock()
    tokenizer.encode.side_effect = [[10], [20]]
    tokenizer.return_value = {'input_ids': [[30]]}
    with pytest.raises(ValueError, match='q / d'):
        prepare_inputs(tokenizer, 'task', [('a', 'b')], [{'query': 'q', 'document': 'd'}], 2)
    tokenizer.pad.assert_not_called()


@pytest.mark.parametrize('answers', [([[1, 2], [3]]), ([[1], [1]])])
def test_answers_must_be_distinct_single_tokens(answers):
    tokenizer = MagicMock()
    tokenizer.encode.side_effect = answers
    with pytest.raises(ValueError, match='single-token'):
        answer_token_ids(tokenizer)


def test_backend_dispatch_keeps_qwen_out_of_classification_head_loader():
    kwargs = dict(batch_size=4, device='cpu', cache_folder=None, local_files_only=True)
    model = {'backend': 'qwen_causal_lm'}
    with patch('scripts.qwen_reranker.rerank', return_value=([], {})) as scorer:
        assert dispatch_rerank(model, [], [], **kwargs) == ([], {})
    scorer.assert_called_once_with(model, [], [], **kwargs)
    with pytest.raises(ValueError, match='Unsupported'):
        dispatch_rerank({'backend': 'unknown'}, [], [], **kwargs)


def test_instruction_is_required_before_loading_model():
    with pytest.raises(ValueError, match='instruction'):
        rerank({'model': 'unused'}, [], [], batch_size=1, device='cpu',
               cache_folder=None, local_files_only=True)


def test_real_local_qwen_logits_and_left_padding_are_batch_independent(tmp_path):
    import torch
    from transformers import BertTokenizerFast, Qwen3Config, Qwen3ForCausalLM

    torch.manual_seed(17)
    path = tmp_path / 'tiny-qwen'
    path.mkdir()
    (path / 'vocab.txt').write_text(
        '[PAD]\n[UNK]\n[CLS]\n[SEP]\n[MASK]\nblue\ncup\nyes\nno\nred\n'
    )
    vocabulary = {
        token: index for index, token in enumerate((path / 'vocab.txt').read_text().splitlines())
    }
    tokenizer = BertTokenizerFast(vocab=vocabulary)
    assert tokenizer.encode('yes', add_special_tokens=False) == [7]
    tokenizer.save_pretrained(path)
    Qwen3ForCausalLM(Qwen3Config(
        vocab_size=10, hidden_size=16, intermediate_size=32, num_hidden_layers=1,
        num_attention_heads=2, num_key_value_heads=1, head_dim=8,
        max_position_embeddings=512, pad_token_id=0, eos_token_id=3,
    )).save_pretrained(path)
    rows = [
        {'id': 'q', 'text': 'blue cup'}, {'id': 'd', 'text': 'red cup'},
        {'id': 'long', 'text': 'blue cup ' * 12},
    ]
    pairs = [{'query': 'q', 'document': 'd'}, {'query': 'long', 'document': 'q'}]
    model = {'model': str(path), 'instruction': 'Check item identity.', 'max_length': 512}
    options = dict(device='cpu', cache_folder=None, local_files_only=True)
    single, timing = rerank(model, rows, pairs, batch_size=1, **options)
    batched, _ = rerank(model, rows, pairs, batch_size=2, **options)
    assert [p['score'] for p in single] == pytest.approx([p['score'] for p in batched], abs=1e-5)
    assert timing['score_type'].startswith('yes_logit_minus_no_logit')
    assert timing['max_pair_tokens'] <= 512
    assert timing['dtype'] == 'torch.float32'

    from transformers import AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(path, padding_side='left', local_files_only=True)
    encoded, _ = prepare_inputs(tokenizer, model['instruction'], [('blue cup', 'red cup')], pairs[:1], 512)
    with torch.inference_mode():
        logits = Qwen3ForCausalLM.from_pretrained(path).eval()(
            **encoded, logits_to_keep=1, use_cache=False,
        ).logits[0, -1]
    no_id, yes_id = answer_token_ids(tokenizer)
    assert single[0]['score'] == pytest.approx((logits[yes_id] - logits[no_id]).item(), abs=1e-5)
