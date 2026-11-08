"""Real spaCy and WordNet behavior, not a hand-written domain vocabulary."""
from dataclasses import replace
import hashlib

import pytest

from library.keyword_matching import common_keywords
from library.text_analysis_types import AnalysisError, AnalysisResult
from library.text_keywords import KeywordExtractor


@pytest.fixture(scope='module')
def extractor():
    return KeywordExtractor()


def result(extractor, text):
    keys, attributes = extractor.extract([text], [text])
    return AnalysisResult(
        source_language='EN', source_hash=hashlib.sha256(text.encode()).hexdigest(),
        translated_text=text, keywords=keys, attributes=attributes,
        profile_fingerprint='same-profile',
    )


def test_unregistered_noun_inflections_and_phrases(extractor):
    left = result(extractor, 'Purple dinosaur keychains.')
    right = result(extractor, 'Purple dinosaur keychain.')
    assert left.keywords == right.keywords
    assert {'lemma:dinosaur', 'lemma:keychain', 'phrase:purple dinosaur keychain'} <= set(left.keywords)


def test_wordnet_synonyms_match_without_a_manual_alias(extractor):
    left, right = result(extractor, 'A sofa.'), result(extractor, 'A couch.')
    assert 'lemma:sofa' in left.keywords and 'lemma:couch' in right.keywords
    assert common_keywords(left, right) == ('wn:sofa.n.01',)
    assert 'aliases' not in extractor.rules


def test_upper_concept_does_not_turn_different_objects_into_synonyms(extractor):
    assert not common_keywords(result(extractor, 'A dog.'), result(extractor, 'A cat.'))
    assert not common_keywords(result(extractor, 'A sofa.'), result(extractor, 'A chair.'))


def test_wordnet_uses_one_pos_compatible_sense_not_all_senses(extractor):
    data = result(extractor, 'A bank.')
    assert sum(key.startswith('wn:') for key in data.keywords) <= 1
    assert len(data.attributes['synsets']) <= 1


def test_negated_synonym_is_not_a_positive_match(extractor):
    assert not common_keywords(result(extractor, 'No couch.'), result(extractor, 'A sofa.'))
    contradictory = result(extractor, 'A sofa. No couch.')
    assert 'wn:sofa.n.01' not in contradictory.keywords
    assert 'lemma:sofa' not in contradictory.keywords


def test_dependency_negation_and_adversative_boundary(extractor):
    data = result(extractor, 'Not red but blue wallet.')
    assert {'lemma:blue', 'lemma:wallet'} <= set(data.keywords)
    assert 'lemma:red' not in data.keywords
    assert 'lemma:red' in data.attributes['negated']
    data = result(extractor, 'A bag without a strap.')
    assert 'lemma:bag' in data.keywords and 'lemma:strap' not in data.keywords


def test_participle_description_is_preserved_and_brand_model_number_survive(extractor):
    data = result(extractor, 'A scratched Sony WH-1000XM5 headphone with mark 1234.')
    assert {'lemma:scratched', 'lemma:sony', 'identifier:wh1000xm5', 'number:1234'} <= set(data.keywords)


@pytest.mark.parametrize('text,expected', [
    ('黒い財布です。', 'term:黒い財布です'), ('黑色钱包', 'term:黑色钱包'),
    ('محفظة سوداء', 'term:محفظة'), ('portefeuille noir', 'lemma:portefeuille'),
])
def test_assumed_english_fallback_does_not_discard_foreign_words(extractor, text, expected):
    assert expected in result(extractor, text).keywords


def test_profiles_cannot_be_silently_mixed(extractor):
    left = result(extractor, 'A sofa.')
    with pytest.raises(AnalysisError, match='KEYWORD_PROFILE_MISMATCH'):
        common_keywords(left, replace(left, profile_fingerprint='old-v1-profile'))


def test_missing_wordnet_assets_are_not_silently_ignored(monkeypatch, tmp_path):
    monkeypatch.setenv('TEXT_ANALYSIS_NLP_DIR', str(tmp_path))
    with pytest.raises(AnalysisError, match='KEYWORD_ASSETS_INVALID'):
        KeywordExtractor()
