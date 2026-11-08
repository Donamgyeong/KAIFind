"""Immutable analysis identity and explicit first-time policy activation."""
import hashlib

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from library.text_analysis_types import AnalysisError, canonical_json
from model import MatchingPolicy, MatchingRuntime, TextAnalysisProfile


POLICY_RULE = 'category-kst-building-or-keyword-v1'
POLICY_CONFIG = {
    'category': 'equal', 'found_date_timezone': 'Asia/Seoul',
    'found_date_minimum': 'lost_date_from', 'lost_date_to_upper_bound': False,
    'evidence': 'building_or_canonical_keyword',
}


def fingerprint(value):
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def validate_profile(profile):
    values = dict(profile)
    expected = values.pop('fingerprint')
    if fingerprint(values) != expected:
        raise AnalysisError('PROFILE_FINGERPRINT_INVALID')
    return values


async def active_policy(db, expected_profile=None):
    row = (await db.execute(
        select(MatchingPolicy, TextAnalysisProfile)
        .join(MatchingRuntime, MatchingRuntime.active_policy_id == MatchingPolicy.id)
        .join(TextAnalysisProfile, TextAnalysisProfile.id == MatchingPolicy.analysis_profile_id)
        .where(MatchingRuntime.id == 1)
    )).first()
    if row is None:
        raise AnalysisError('MATCHING_POLICY_NOT_CONFIGURED')
    policy, profile = row
    stored = {key: getattr(profile, key) for key in (
        'model_name', 'model_revision', 'tokenizer_revision', 'input_format_version',
        'language_rule_version', 'keyword_rule_version', 'runtime_config', 'fingerprint',
    )}
    validate_profile(stored)
    identity = {
        'analysis_profile_fingerprint': profile.fingerprint,
        'rule_version': policy.rule_version, 'config': policy.config,
    }
    if (policy.rule_version != POLICY_RULE or policy.config != POLICY_CONFIG
            or fingerprint(identity) != policy.fingerprint):
        raise AnalysisError('MATCHING_POLICY_INVALID')
    if expected_profile is not None:
        validate_profile(expected_profile)
        if stored != expected_profile:
            raise AnalysisError('ANALYSIS_PROFILE_MISMATCH')
    return policy, profile


async def initialize_policy(db, profile, *, now):
    """Caller commits. Never replaces an already active policy."""
    values = validate_profile(profile)
    await db.execute(insert(TextAnalysisProfile).values(
        name='analysis-' + profile['fingerprint'], **values,
        fingerprint=profile['fingerprint'], created_at=now,
    ).on_conflict_do_nothing(index_elements=['fingerprint']))
    stored = (await db.execute(select(TextAnalysisProfile).where(
        TextAnalysisProfile.fingerprint == profile['fingerprint'],
    ))).scalar_one()
    identity = {
        'analysis_profile_fingerprint': profile['fingerprint'],
        'rule_version': POLICY_RULE, 'config': POLICY_CONFIG,
    }
    digest = fingerprint(identity)
    await db.execute(insert(MatchingPolicy).values(
        analysis_profile_id=stored.id, rule_version=POLICY_RULE,
        config=POLICY_CONFIG, fingerprint=digest, created_at=now,
    ).on_conflict_do_nothing(index_elements=['fingerprint']))
    policy_id = (await db.execute(select(MatchingPolicy.id).where(
        MatchingPolicy.fingerprint == digest,
    ))).scalar_one()
    await db.execute(insert(MatchingRuntime).values(
        id=1, active_policy_id=policy_id, generation=1, updated_at=now,
    ).on_conflict_do_nothing(index_elements=['id']))
    return await active_policy(db, profile)
