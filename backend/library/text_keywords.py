"""General spaCy lemmas/phrases and bounded WordNet synonym-set features."""
from functools import lru_cache
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import re
import unicodedata

from library.keyword_resources import (
    SPACY_MODEL, SPACY_MODEL_VERSION, directory_hash, resource_directory, verify_wordnet,
)
from library.text_analysis_types import AnalysisError, canonical_json


RULES_PATH = Path(__file__).with_name('data') / 'text_keyword_rules.json'
IDENTIFIER = re.compile(r'(?=.*[a-z])(?=.*[0-9])[a-z0-9]+(?:-[a-z0-9]+)*\Z')
CONTENT_POS = {'NOUN', 'PROPN', 'ADJ'}


class KeywordExtractor:
    def __init__(self):
        self.rules = json.loads(RULES_PATH.read_text())
        if (self.rules.get('wordnet_sense_policy') != 'first-pos-sense'
                or self.rules.get('wordnet_relations') != ['synset-only']
                or not 2 <= self.rules.get('max_phrase_tokens', 0) <= 10):
            raise AnalysisError('KEYWORD_POLICY_INVALID')
        self.rules_hash = hashlib.sha256(canonical_json(self.rules).encode()).hexdigest()
        manifest = verify_wordnet(resource_directory())
        try:
            import nltk
            import spacy
            from nltk.corpus import wordnet

            if version('en-core-web-sm') != SPACY_MODEL_VERSION:
                raise AnalysisError('KEYWORD_MODEL_VERSION_MISMATCH')
            nltk.data.path.insert(0, str(resource_directory().resolve()))
            wordnet.ensure_loaded()
            expected = str((resource_directory() / 'corpora' / 'wordnet.zip').resolve()) + '/'
            if not str(wordnet.root).startswith(expected) or wordnet.get_version() != '3.0':
                raise AnalysisError('KEYWORD_CORPUS_CONFLICT')
            self._wn = wordnet
            self._nlp = spacy.load(SPACY_MODEL, exclude=['ner'])
            reader = self._wn
            self._lookup = lru_cache(maxsize=4096)(
                lambda word, pos=None: tuple(reader.synsets(word, pos=pos))
            )
            self.resources = {
                'spacy_model': SPACY_MODEL, 'spacy_model_version': SPACY_MODEL_VERSION,
                'spacy_model_sha256': directory_hash(self._nlp.path),
                'wordnet': manifest, 'policy_sha256': self.rules_hash,
            }
            self._lookup('wallet', 'n')
            self._nlp('a black wallet')
        except AnalysisError:
            raise
        except Exception:
            raise AnalysisError('KEYWORD_RESOURCES_UNAVAILABLE') from None

    @staticmethod
    def _normalize(value):
        return unicodedata.normalize('NFKC', value).lower()

    def _negated(self, doc):
        indices = set()
        for token in doc:
            if token.lower_ not in self.rules['negators']:
                continue
            if token.lower_ == 'without':
                roots = [child for child in token.children if child.dep_ in {'pobj', 'obj', 'pcomp'}]
            else:
                roots = [token.head]
            boundary = next((word.i for word in token.sent if word.i > token.i
                             and word.lower_ in self.rules['negation_breaks']), token.sent.end)
            if not roots:
                indices.update(word.i for word in token.sent if token.i < word.i < boundary)
            for root in roots:
                indices.update(word.i for word in root.subtree if word.i < boundary)
        return indices

    def _feature(self, token):
        word = self._normalize(token.text)
        if IDENTIFIER.fullmatch(word):
            return 'identifier:' + word.replace('-', ''), None
        if word.isdecimal():
            return 'number:' + word, None
        if not any(character.isalpha() for character in word) or token.is_stop:
            return None, None
        if not word.isascii():
            return 'term:' + word, None

        adjectival_verb = token.pos_ == 'VERB' and token.dep_ in {'amod', 'acl'}
        lemma = word if adjectival_verb else self._normalize(token.lemma_ or word)
        unknown = not self._lookup(lemma)
        if token.pos_ not in CONTENT_POS and not adjectival_verb and token.pos_ != 'X' and not unknown:
            return None, None
        # Proper names and unrecognized words are retained but never guessed
        # into a WordNet sense. Participles retain their descriptive surface form.
        pos = 'n' if token.pos_ == 'NOUN' else 'a' if token.pos_ == 'ADJ' or adjectival_verb else None
        return 'lemma:' + lemma, pos

    def _expand(self, key, pos, selected):
        if pos is None:
            return {key}
        lemma = key.split(':', 1)[1].replace(' ', '_')
        senses = self._lookup(lemma, pos)
        if not senses:
            return {key}
        # First POS-compatible sense only. No cross-sense union, hypernyms,
        # hyponyms or recursive expansion. This is not contextual WSD.
        sense = senses[0].name()
        selected[key] = sense
        return {key, 'wn:' + sense}

    def _scan(self, value, selected):
        doc = self._nlp(unicodedata.normalize('NFKC', value))
        negated = self._negated(doc)
        features = {}
        for token in doc:
            key, pos = self._feature(token)
            if key:
                features[token.i] = key
                yield self._expand(key, pos, selected), token.i in negated

        for chunk in doc.noun_chunks:
            parts = [token for token in chunk if token.i in features and token.pos_ in CONTENT_POS]
            if not 2 <= len(parts) <= self.rules['max_phrase_tokens']:
                continue
            # A phrase crossing a negation boundary is not a positive feature.
            phrase = ' '.join(features[token.i].split(':', 1)[1] for token in parts)
            key = 'phrase:' + phrase
            yield self._expand(key, 'n', selected), any(token.i in negated for token in parts)

    def extract(self, translated_fields: list[str], original_fields: list[str]):
        positive, negative, selected = set(), set(), {}
        for field in translated_fields:
            for keys, negated in self._scan(field, selected):
                (negative if negated else positive).update(keys)

        # Protect source identifiers/numbers and ASCII proper names from
        # translation loss without bypassing translation for Korean nouns.
        for field in original_fields:
            doc = self._nlp(unicodedata.normalize('NFKC', field))
            negated = self._negated(doc)
            for token in doc:
                word = self._normalize(token.text)
                if IDENTIFIER.fullmatch(word):
                    key = 'identifier:' + word.replace('-', '')
                elif word.isdecimal():
                    key = 'number:' + word
                elif token.pos_ == 'PROPN' and word.isascii() and word.isalpha() and not token.is_stop:
                    key = 'lemma:' + word
                else:
                    continue
                (negative if token.i in negated else positive).add(key)
        negative_senses = {key for key in negative if key.startswith('wn:')}
        positive -= negative
        positive = {key for key in positive if 'wn:' + selected.get(key, '') not in negative_senses}
        attributes = {
            'lemmas': sorted(key[6:] for key in positive if key.startswith('lemma:')),
            'phrases': sorted(key[7:] for key in positive if key.startswith('phrase:')),
            'synsets': dict(sorted(selected.items())),
            'negated': sorted(negative),
        }
        return tuple(sorted(positive)), attributes
