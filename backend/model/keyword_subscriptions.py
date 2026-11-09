"""Versioned subscription terms and immutable registration work."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, Text,
    UniqueConstraint, Uuid, text,
)
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDPrimaryKey


class KeywordSubscriptionFeature(UUIDPrimaryKey, Base):
    __tablename__ = 'keyword_subscription_features'
    __table_args__ = (
        UniqueConstraint('subscription_id', 'profile_id', 'rule_version'),
        CheckConstraint("status IN ('READY','FAILED')", name='status'),
        CheckConstraint("(status = 'READY' AND terms IS NOT NULL AND cardinality(terms) > 0 AND last_error_code IS NULL) OR "
                        "(status = 'FAILED' AND terms IS NULL AND last_error_code IS NOT NULL)", name='result'),
        CheckConstraint('terms IS NULL OR array_position(terms, NULL) IS NULL', name='terms'),
    )
    subscription_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('keyword_subscriptions.id', ondelete='CASCADE'))
    profile_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('text_analysis_profiles.id', ondelete='RESTRICT'))
    rule_version: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    terms: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    source_hash: Mapped[str] = mapped_column(Text)
    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)


class KeywordRegistrationEvent(UUIDPrimaryKey, Base):
    __tablename__ = 'keyword_registration_events'
    __table_args__ = (
        UniqueConstraint('item_id'),
        CheckConstraint("status IN ('PENDING','READY','DONE','CANCELLED','FAILED')", name='status'),
        CheckConstraint('(lease_token IS NULL) = (lease_until IS NULL)', name='lease'),
        CheckConstraint('attempts >= 0', name='attempts'),
        CheckConstraint('terms IS NULL OR array_position(terms, NULL) IS NULL', name='terms'),
        CheckConstraint("status <> 'READY' OR (terms IS NOT NULL AND profile_id IS NOT NULL)", name='ready'),
    )
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey('found_items.id', ondelete='CASCADE'))
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    registration_order: Mapped[int] = mapped_column(BigInteger)
    profile_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey('text_analysis_profiles.id', ondelete='RESTRICT'))
    rule_version: Mapped[str] = mapped_column(Text, server_default=text("'all-atomic-terms-v1'"))
    status: Mapped[str] = mapped_column(Text, server_default=text("'PENDING'"))
    source_title: Mapped[str | None] = mapped_column(Text)
    source_description: Mapped[str | None] = mapped_column(Text)
    source_hash: Mapped[str | None] = mapped_column(Text)
    terms: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    cursor_user_id: Mapped[UUID | None] = mapped_column(Uuid)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text('now()'))
    lease_token: Mapped[UUID | None] = mapped_column(Uuid)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    failed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_code: Mapped[str | None] = mapped_column(Text)
