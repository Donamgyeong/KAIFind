"""Subscription-only all-word rules, independent of analysis profile identity."""


SUBSCRIPTION_RULE = 'all-atomic-terms-v1'
ATOMIC_PREFIXES = ('lemma:', 'term:', 'identifier:', 'number:')


def atomic_terms(keywords):
    """Exclude phrase and synset expansions from required word conditions."""
    return tuple(sorted({key for key in keywords if key.startswith(ATOMIC_PREFIXES)}))


def all_terms_match(subscription_terms, item_terms):
    required = set(atomic_terms(subscription_terms))
    return bool(required) and required.issubset(atomic_terms(item_terms))
