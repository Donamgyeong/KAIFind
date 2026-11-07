"""Versioned text analysis and durable matching work; inference lives in services."""
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text,
    UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDPrimaryKey


class TextAnalysisProfile(UUIDPrimaryKey, Base):
    __tablename__ = 'text_analysis_profiles'
    __table_args__ = (
        CheckConstraint("btrim(name) <> ''", name='name_nonblank'),
        CheckConstraint("btrim(model_name) <> ''", name='model_name_nonblank'),
        CheckConstraint("model_revision ~ '^[0-9a-f]{40}$'", name='model_revision_commit'),
        CheckConstraint("tokenizer_revision ~ '^[0-9a-f]{40}$'", name='tokenizer_revision_commit'),
        CheckConstraint("btrim(input_format_version) <> ''", name='input_format_nonblank'),
        CheckConstraint("btrim(language_rule_version) <> ''", name='language_rule_nonblank'),
        CheckConstraint("btrim(keyword_rule_version) <> ''", name='keyword_rule_nonblank'),
        CheckConstraint("jsonb_typeof(runtime_config) = 'object'", name='runtime_object'),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name='fingerprint_sha256'),
    )
    name: Mapped[str] = mapped_column(Text, unique=True)
    model_name: Mapped[str] = mapped_column(Text)
    model_revision: Mapped[str] = mapped_column(Text)
    tokenizer_revision: Mapped[str] = mapped_column(Text)
    input_format_version: Mapped[str] = mapped_column(Text)
    language_rule_version: Mapped[str] = mapped_column(Text)
    keyword_rule_version: Mapped[str] = mapped_column(Text)
    runtime_config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))


class MatchingPolicy(UUIDPrimaryKey, Base):
    __tablename__ = 'matching_policies'
    __table_args__ = (
        UniqueConstraint('id', 'analysis_profile_id', name='uq_matching_policies_id_profile'),
        CheckConstraint("btrim(rule_version) <> ''", name='rule_nonblank'),
        CheckConstraint("jsonb_typeof(config) = 'object'", name='config_object'),
        CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name='fingerprint_sha256'),
    )
    analysis_profile_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey('text_analysis_profiles.id', ondelete='RESTRICT'))
    rule_version: Mapped[str] = mapped_column(Text)
    config: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fingerprint: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))


class MatchingRuntime(Base):
    __tablename__ = 'matching_runtime'
    __table_args__ = (
        CheckConstraint('id = 1', name='singleton'),
        CheckConstraint('generation > 0', name='generation_positive'),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    active_policy_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('matching_policies.id', ondelete='RESTRICT'))
    generation: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))


class TextFeatureColumns:
    profile_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('text_analysis_profiles.id', ondelete='RESTRICT'))
    text_version: Mapped[int] = mapped_column(BigInteger)
    source_hash: Mapped[str] = mapped_column(Text)
    source_language: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, server_default='PENDING')
    translated_text: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    attributes: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)


def feature_constraints(owner_column):
    return (
        UniqueConstraint(owner_column, 'profile_id', 'text_version'),
        UniqueConstraint('id', owner_column, 'profile_id', name=f'uq_{owner_column}_feature_identity'),
        CheckConstraint('text_version > 0', name='text_version_positive'),
        CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name='source_hash_sha256'),
        CheckConstraint("source_language IN ('KO','EN','MIXED')", name='source_language'),
        CheckConstraint("status IN ('PENDING','PROCESSING','READY','FAILED','SUPERSEDED')", name='status'),
        CheckConstraint(
            "(status = 'READY' AND translated_text IS NOT NULL AND keywords IS NOT NULL "
            "AND attributes IS NOT NULL AND completed_at IS NOT NULL AND last_error_code IS NULL) OR "
            "(status <> 'READY' AND translated_text IS NULL AND keywords IS NULL AND attributes IS NULL)",
            name='result_state'),
        CheckConstraint(
            "(status IN ('PENDING','PROCESSING') AND completed_at IS NULL AND last_error_code IS NULL) OR "
            "(status = 'FAILED' AND completed_at IS NOT NULL AND last_error_code IS NOT NULL) OR "
            "(status IN ('READY','SUPERSEDED') AND completed_at IS NOT NULL AND last_error_code IS NULL)",
            name='completion_state'),
        CheckConstraint("attributes IS NULL OR jsonb_typeof(attributes) = 'object'", name='attributes_object'),
        CheckConstraint(
            "keywords IS NULL OR (coalesce(array_ndims(keywords), 1) = 1 "
            "AND array_position(keywords, NULL) IS NULL)", name='keywords_shape'),
        CheckConstraint("last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'", name='error_code'),
    )


class FoundItemTextFeature(UUIDPrimaryKey, TextFeatureColumns, Base):
    __tablename__ = 'found_item_text_features'
    __table_args__ = feature_constraints('item_id')
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('found_items.id', ondelete='CASCADE'))


class LostReportTextFeature(UUIDPrimaryKey, TextFeatureColumns, Base):
    __tablename__ = 'lost_report_text_features'
    __table_args__ = feature_constraints('report_id')
    report_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('lost_reports.id', ondelete='CASCADE'))


class MatchEvaluationJob(UUIDPrimaryKey, Base):
    __tablename__ = 'match_evaluation_jobs'
    __table_args__ = (
        UniqueConstraint('item_id', 'policy_id'),
        UniqueConstraint('report_id', 'policy_id'),
        CheckConstraint('(item_id IS NULL) <> (report_id IS NULL)', name='one_owner'),
        CheckConstraint('requested_generation > 0 AND completed_generation >= 0 '
                        'AND completed_generation <= requested_generation', name='generations'),
        CheckConstraint(
            '(claimed_generation IS NULL AND lease_token IS NULL AND lease_until IS NULL) OR '
            '(claimed_generation IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL '
            'AND claimed_generation >= 1 AND claimed_generation <= requested_generation)', name='lease'),
        CheckConstraint('attempts >= 0', name='attempts'),
        CheckConstraint('(failed_at IS NULL) = (last_error_code IS NULL)', name='failure'),
        CheckConstraint('failed_at IS NULL OR lease_token IS NULL', name='failed_lease'),
        CheckConstraint("last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'", name='error_code'),
    )
    item_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('found_items.id', ondelete='CASCADE'))
    report_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('lost_reports.id', ondelete='CASCADE'))
    policy_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('matching_policies.id', ondelete='RESTRICT'))
    requested_generation: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    completed_generation: Mapped[int] = mapped_column(BigInteger, server_default=text('0'))
    claimed_generation: Mapped[int | None] = mapped_column(BigInteger)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
