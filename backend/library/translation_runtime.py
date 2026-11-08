"""One resident Marian model, owned and used by one inference thread."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from dataclasses import dataclass
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import threading
import time

from library.text_analysis_types import (
    AnalysisError, AnalysisInput, AnalysisResult, INPUT_FORMAT_VERSION,
    KEYWORD_RULE_VERSION, LANGUAGE_RULE_VERSION, MODEL_ID, MODEL_REVISION, canonical_json,
)
from library.text_input import needs_translation, source_language
from library.text_keywords import KeywordExtractor


REQUIRED_ASSETS = ('config.json', 'model.safetensors', 'source.spm', 'target.spm', 'vocab.json')
OPTIONAL_ASSETS = ('generation_config.json', 'tokenizer_config.json', 'special_tokens_map.json', 'added_tokens.json')
PACKAGES = (
    'torch', 'transformers', 'sentencepiece', 'sacremoses', 'safetensors',
    'huggingface-hub', 'tokenizers', 'spacy', 'nltk', 'en-core-web-sm',
)


@dataclass(frozen=True)
class TranslationSettings:
    model_directory: Path = Path('/app/.cache/text-analysis')
    input_tokens: int = 128
    output_tokens: int = 255
    max_chunks: int = 32
    timeout_seconds: float = 30
    shutdown_seconds: float = 10
    startup_seconds: float = 120
    cpu_threads: int = 1

    def __post_init__(self):
        if not 8 <= self.input_tokens <= 256 or not 2 <= self.output_tokens <= 255:
            raise ValueError('Invalid translation token limits')
        if not 1 <= self.max_chunks <= 128 or not 1 <= self.cpu_threads <= 8:
            raise ValueError('Invalid translation resource limits')
        if not 0 < self.timeout_seconds <= 300 or not 0 < self.shutdown_seconds <= 60:
            raise ValueError('Invalid translation time limits')
        if not 0 < self.startup_seconds <= 300:
            raise ValueError('Invalid startup time limit')

    @classmethod
    def from_environment(cls):
        return cls(
            model_directory=Path(os.getenv('TEXT_ANALYSIS_MODEL_DIR', '/app/.cache/text-analysis')),
            timeout_seconds=float(os.getenv('TEXT_ANALYSIS_TIMEOUT_SECONDS', '30')),
            cpu_threads=int(os.getenv('TEXT_ANALYSIS_CPU_THREADS', '1')),
        )


def verify_assets(directory: Path) -> dict:
    try:
        manifest = json.loads((directory / 'assets.json').read_text())
        if manifest['model_name'] != MODEL_ID or manifest['revision'] != MODEL_REVISION:
            raise ValueError('Unexpected model')
        files = manifest['files']
        if not set(REQUIRED_ASSETS) <= files.keys():
            raise ValueError('Missing assets')
        if not files.keys() <= set(REQUIRED_ASSETS + OPTIONAL_ASSETS):
            raise ValueError('Unexpected assets')
        actual_files = {path.name for path in directory.iterdir() if path.is_file()}
        if actual_files != set(files) | {'assets.json'}:
            raise ValueError('Unrecorded files')
        for name, expected in files.items():
            if Path(name).name != name or not re.fullmatch('[0-9a-f]{64}', expected):
                raise ValueError('Invalid asset entry')
            actual = hashlib.sha256((directory / name).read_bytes()).hexdigest()
            if actual != expected:
                raise ValueError('Asset mismatch')
        return manifest
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        raise AnalysisError('MODEL_ASSETS_INVALID') from None


class TranslationRuntime:
    def __init__(self, settings: TranslationSettings):
        self.settings = settings
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='text-analysis')
        self._gate = asyncio.Lock()
        self._stop = threading.Event()
        self._future = None
        self._model = None
        self._tokenizer = None
        self._extractor = None
        self._profile = None
        self._generation_config = None
        self._closed = False
        self._shutdown = False
        self._drained = False
        self.ready = False
        self.thread_id = None
        self.load_count = 0

    @property
    def profile(self):
        if not self.ready:
            raise AnalysisError('MODEL_NOT_READY', retryable=True)
        return json.loads(canonical_json(self._profile))

    async def start(self):
        if self._closed or self._future is not None:
            raise AnalysisError('INVALID_RUNTIME_STATE')
        self._future = asyncio.get_running_loop().run_in_executor(self._executor, self._load)
        self._future.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
        try:
            await asyncio.wait_for(asyncio.shield(self._future), self.settings.startup_seconds)
            if self._closed:
                raise AnalysisError('ANALYSIS_STOPPED', retryable=True)
            self.ready = True
        except asyncio.TimeoutError:
            await self.close()
            raise AnalysisError('MODEL_STARTUP_TIMEOUT', retryable=True) from None
        except AnalysisError:
            await self.close()
            raise
        except Exception:
            await self.close()
            raise AnalysisError('MODEL_LOAD_FAILED') from None
        except BaseException:
            await self.close()
            raise

    def _load(self):
        manifest = verify_assets(self.settings.model_directory)
        try:
            import torch
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

            self.thread_id = threading.get_ident()
            torch.set_num_threads(self.settings.cpu_threads)
            self._tokenizer = AutoTokenizer.from_pretrained(
                self.settings.model_directory, local_files_only=True, trust_remote_code=False,
            )
            self._model = AutoModelForSeq2SeqLM.from_pretrained(
                self.settings.model_directory, local_files_only=True,
                use_safetensors=True, dtype=torch.float32, trust_remote_code=False,
            ).to('cpu').eval()
            self._generation_config = deepcopy(self._model.generation_config)
            self._generation_config.max_length = None  # Only max_new_tokens controls output.
            self._generation_config.max_new_tokens = self.settings.output_tokens
            self._generation_config.do_sample = False
            self._generation_config.num_beams = 1
            self._generation_config.forced_eos_token_id = None
            # v5 fills None entries from model.generation_config. Override that
            # source too so it cannot silently re-enable forced EOS at the cap.
            self._model.generation_config = deepcopy(self._generation_config)
            self._extractor = KeywordExtractor()
            if self.settings.input_tokens > self._model.config.max_position_embeddings:
                raise AnalysisError('MODEL_INPUT_LIMIT_INVALID')
            self.load_count += 1
            self._translate('검은 지갑', time.monotonic() + self.settings.timeout_seconds)
        except AnalysisError:
            raise
        except Exception:
            raise AnalysisError('MODEL_LOAD_FAILED') from None

        config = {
            'dependencies': {name: version(name) for name in PACKAGES},
            'device': 'cpu', 'dtype': 'float32', 'cpu_threads': self.settings.cpu_threads,
            'input_tokens': self.settings.input_tokens, 'output_tokens': self.settings.output_tokens,
            'max_chunks': self.settings.max_chunks, 'timeout_seconds': self.settings.timeout_seconds,
            'do_sample': False, 'num_beams': 1, 'forced_eos_token_id': None,
            'generation_config': self._generation_config.to_dict(),
            'chunking': 'sentence-pack-token-fallback-v1',
            'keyword_rules_sha256': self._extractor.rules_hash,
            'keyword_resources': self._extractor.resources,
            'assets': manifest['files'],
            'implementation_sha256': {
                name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                for name in ('translation_runtime.py', 'text_input.py', 'text_keywords.py',
                             'text_analysis_types.py', 'keyword_resources.py', 'keyword_matching.py')
            },
        }
        self._profile = {
            'model_name': MODEL_ID, 'model_revision': MODEL_REVISION,
            'tokenizer_revision': MODEL_REVISION, 'input_format_version': INPUT_FORMAT_VERSION,
            'language_rule_version': LANGUAGE_RULE_VERSION, 'keyword_rule_version': KEYWORD_RULE_VERSION,
            'runtime_config': config,
        }
        self._profile['fingerprint'] = hashlib.sha256(canonical_json(self._profile).encode()).hexdigest()

    def _translate(self, value: str, deadline: float) -> str:
        if not needs_translation(value):
            return value
        import torch
        from transformers import StoppingCriteria, StoppingCriteriaList

        stop = self._stop

        class Deadline(StoppingCriteria):
            def __call__(self, input_ids, scores, **kwargs):
                return stop.is_set() or time.monotonic() >= deadline

        budget = self.settings.input_tokens - self._tokenizer.num_special_tokens_to_add(pair=False)
        chunks, current = [], []
        for sentence in re.split(r'(?<=[.!?。！？])\s*|\n+', value):
            ids = self._tokenizer.encode(sentence, add_special_tokens=False)
            if len(current) + len(ids) > budget and current:
                chunks.append(current)
                current = []
            while len(ids) > budget:
                chunks.append(ids[:budget])
                ids = ids[budget:]
            current.extend(ids)
        if current:
            chunks.append(current)
        if len(chunks) > self.settings.max_chunks:
            raise AnalysisError('TEXT_CHUNK_LIMIT')

        outputs = []
        for chunk in chunks:
            if stop.is_set():
                raise AnalysisError('ANALYSIS_STOPPED', retryable=True)
            if time.monotonic() >= deadline:
                raise AnalysisError('ANALYSIS_TIMEOUT', retryable=True)
            batch = self._tokenizer.prepare_for_model(
                chunk, add_special_tokens=True, return_tensors='pt',
                return_token_type_ids=False, return_attention_mask=True,
            )
            batch = {name: tensor.unsqueeze(0) for name, tensor in batch.items()}
            with torch.inference_mode():
                generated = self._model.generate(
                    **batch, generation_config=self._generation_config,
                    stopping_criteria=StoppingCriteriaList([Deadline()]),
                )[0]
            if stop.is_set():
                raise AnalysisError('ANALYSIS_STOPPED', retryable=True)
            if time.monotonic() >= deadline:
                raise AnalysisError('ANALYSIS_TIMEOUT', retryable=True)
            if (generated[-1].item() != self._tokenizer.eos_token_id
                    or len(generated) - 1 >= self.settings.output_tokens):
                raise AnalysisError('TRANSLATION_OUTPUT_LIMIT')
            translated = self._tokenizer.decode(generated, skip_special_tokens=True).strip()
            if not translated:
                raise AnalysisError('TRANSLATION_EMPTY')
            outputs.append(translated)
        return ' '.join(outputs)

    def _analyze(self, value: AnalysisInput) -> AnalysisResult:
        if threading.get_ident() != self.thread_id:
            raise AnalysisError('INVALID_INFERENCE_THREAD')
        try:
            deadline = time.monotonic() + self.settings.timeout_seconds
            translated = {
                'title': self._translate(value.title, deadline) if value.title else None,
                'description': self._translate(value.description, deadline),
            }
            originals = [field for field in (value.title, value.description) if field]
            keywords, attributes = self._extractor.extract(
                [field for field in translated.values() if field], originals,
            )
            return AnalysisResult(
                source_language=source_language('\n'.join(originals)), source_hash=value.source_hash,
                translated_text=canonical_json(translated), keywords=keywords, attributes=attributes,
                profile_fingerprint=self._profile['fingerprint'],
            )
        except AnalysisError:
            raise
        except Exception:
            raise AnalysisError('ANALYSIS_FAILED', retryable=True) from None

    async def analyze(self, value: AnalysisInput) -> AnalysisResult:
        if not isinstance(value, AnalysisInput):
            raise AnalysisError('INVALID_TEXT_INPUT')
        if not self.ready or self._closed:
            raise AnalysisError('MODEL_NOT_READY', retryable=True)
        if self._gate.locked() or (self._future is not None and not self._future.done()):
            raise AnalysisError('ANALYSIS_BUSY', retryable=True)

        async with self._gate:
            self._future = asyncio.get_running_loop().run_in_executor(self._executor, self._analyze, value)
            # Consume a late exception even when the caller has timed out/cancelled.
            self._future.add_done_callback(lambda future: future.exception() if not future.cancelled() else None)
            try:
                return await asyncio.wait_for(asyncio.shield(self._future), self.settings.timeout_seconds)
            except asyncio.TimeoutError:
                raise AnalysisError('ANALYSIS_TIMEOUT', retryable=True) from None

    async def close(self) -> bool:
        if self._shutdown:
            return self._drained
        self.ready = False
        self._closed = True
        self._stop.set()
        drained = True
        if self._future is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._future), self.settings.shutdown_seconds)
            except asyncio.TimeoutError:
                drained = False
            except Exception:
                pass
        if drained:
            await asyncio.get_running_loop().run_in_executor(self._executor, self._release)
            self._future = None
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._shutdown = True
        self._drained = drained
        return drained

    def _release(self):
        self._model = None
        self._tokenizer = None
        self._extractor = None
        self._generation_config = None
