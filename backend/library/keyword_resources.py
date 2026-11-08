"""Pinned local spaCy/WordNet assets; runtime never downloads NLP resources."""
import hashlib
import json
import os
from pathlib import Path

from library.text_analysis_types import AnalysisError, canonical_json


SPACY_MODEL = 'en_core_web_sm'
SPACY_MODEL_VERSION = '3.8.0'
WORDNET_REVISION = '96f9b3252457a2b97e52aec64c3dfceeb5c312d5'
WORDNET_URL = (
    f'https://raw.githubusercontent.com/nltk/nltk_data/{WORDNET_REVISION}'
    '/packages/corpora/wordnet.zip'
)


def resource_directory() -> Path:
    return Path(os.getenv('TEXT_ANALYSIS_NLP_DIR', '/app/.cache/text-analysis-nlp'))


def verify_wordnet(directory: Path) -> dict:
    try:
        manifest = json.loads((directory / 'assets.json').read_text())
        actual = hashlib.sha256((directory / 'corpora' / 'wordnet.zip').read_bytes()).hexdigest()
        if (manifest['revision'] != WORDNET_REVISION or manifest['version'] != '3.0'
                or manifest['sha256'] != actual):
            raise ValueError('Unexpected WordNet resources')
        return manifest
    except (OSError, ValueError, TypeError, KeyError):
        raise AnalysisError('KEYWORD_ASSETS_INVALID') from None


def directory_hash(directory: Path) -> str:
    files = {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob('*'))
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc'
    }
    return hashlib.sha256(canonical_json(files).encode()).hexdigest()
