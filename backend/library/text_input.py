"""Deterministic routing: any text without Hangul is treated as English."""
import re
import unicodedata


HANGUL = re.compile('[\u1100-\u11ff\u3130-\u318f\ua960-\ua97f\uac00-\ud7af\ud7b0-\ud7ff]')


def needs_translation(value: str) -> bool:
    return HANGUL.search(value) is not None


def source_language(value: str) -> str:
    if not needs_translation(value):
        return 'EN'

    has_other_letters = any(
        unicodedata.category(character).startswith('L') and not HANGUL.fullmatch(character)
        for character in value
    )
    return 'MIXED' if has_other_letters else 'KO'
