"""Internal text analysis values; HTTP request models belong to schema/."""
from dataclasses import dataclass
import hashlib
import json
import unicodedata


MODEL_ID = 'Helsinki-NLP/opus-mt_tiny_kor-eng'
MODEL_REVISION = '755c263bce01f7b1aa9472b32940961fa1efccf3'
INPUT_FORMAT_VERSION = 'title-description-json-v1'
LANGUAGE_RULE_VERSION = 'hangul-or-assumed-english-v1'
KEYWORD_RULE_VERSION = 'spacy-wordnet-keywords-v2'


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


class AnalysisError(Exception):
    """Safe codes only: never include source text or library exception messages."""

    def __init__(self, code: str, *, retryable: bool = False):
        super().__init__(code)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class AnalysisInput:
    description: str
    title: str | None = None

    def __post_init__(self):
        for name, maximum in (('description', 2000), ('title', 100)):
            value = getattr(self, name)
            if name == 'title' and value is None:
                continue
            if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
                raise AnalysisError('INVALID_TEXT_INPUT')
            object.__setattr__(self, name, unicodedata.normalize('NFKC', value.strip()))

    def canonical(self) -> str:
        return canonical_json({'title': self.title, 'description': self.description})

    @property
    def source_hash(self) -> str:
        return hashlib.sha256(self.canonical().encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class AnalysisResult:
    source_language: str
    source_hash: str
    translated_text: str
    keywords: tuple[str, ...]
    attributes: dict
    profile_fingerprint: str
