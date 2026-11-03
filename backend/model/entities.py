"""KAIFind ORM models. Cross-resource authorization belongs in services."""
from datetime import date, datetime
from uuid import UUID
from typing import Any

from sqlalchemy import (BigInteger, Boolean, CheckConstraint, Date, DateTime,
    ForeignKey, ForeignKeyConstraint, Integer, String, Text, UniqueConstraint,
    Uuid, text)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, UUIDPrimaryKey


class User(UUIDPrimaryKey, Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("affiliation IN ('STUDENT','FACULTY','STAFF')", name='affiliation'),
        CheckConstraint("role IN ('MEMBER','ADMIN')", name='role'),
        CheckConstraint("language IN ('ko','en')", name='language'),
    )
    mock_subject: Mapped[str] = mapped_column(Text, unique=True)
    name: Mapped[str] = mapped_column(Text)
    email: Mapped[str] = mapped_column(Text)
    affiliation: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, server_default='MEMBER')
    language: Mapped[str] = mapped_column(Text, server_default='ko')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))
    version: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    __mapper_args__ = {'version_id_col': version}

class Session(UUIDPrimaryKey, Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    csrf_secret_ciphertext: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    idle_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    absolute_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class NotificationSetting(Base):
    __tablename__ = "notification_settings"
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    email_enabled: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    match_email: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    collection_email: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    expiry_email: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    keyword_email: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class Building(UUIDPrimaryKey, Base):
    __tablename__ = "buildings"
    code: Mapped[str] = mapped_column(Text, unique=True)
    name_ko: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class Category(UUIDPrimaryKey, Base):
    __tablename__ = "categories"
    name_ko: Mapped[str] = mapped_column(Text)
    name_en: Mapped[str] = mapped_column(Text)
    sensitive: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class FoundItem(UUIDPrimaryKey, Base):
    __tablename__ = "found_items"
    __table_args__ = (
        CheckConstraint("status IN ('POSTED','COLLECTED','EXPIRED')", name='status'),
        CheckConstraint("(status = 'POSTED') = (closed_at IS NULL)", name='closed_state'),
    )
    finder_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    category_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("categories.id", ondelete="RESTRICT"))
    found_building_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("buildings.id", ondelete="RESTRICT"))
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(2000))
    found_location_description: Mapped[str] = mapped_column(String(300))
    found_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(Text, server_default='POSTED')
    hidden: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))
    posted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    __mapper_args__ = {'version_id_col': version}

class DropOffVersion(UUIDPrimaryKey, Base):
    __tablename__ = "drop_off_versions"
    __table_args__ = (
        CheckConstraint('revision_no > 0', name='revision'),
        CheckConstraint("(mode = 'DROP_OFF' AND building_id IS NOT NULL AND spot_description IS NOT NULL) OR (mode = 'KEPT_BY_FINDER' AND building_id IS NULL AND spot_description IS NULL)", name='location'),
        UniqueConstraint('item_id', 'revision_no'),
        UniqueConstraint('id', 'item_id'),
    )
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("found_items.id", ondelete="CASCADE"))
    revision_no: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(Text)
    building_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("buildings.id", ondelete="RESTRICT"), nullable=True)
    spot_description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    changed_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    sensitive_latched: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))

class Photo(UUIDPrimaryKey, Base):
    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint("purpose IN ('ITEM','DROP_OFF')", name='purpose'),
        CheckConstraint('width > 0 AND height > 0 AND size_bytes > 0', name='dimensions'),
        CheckConstraint("content_type IN ('image/jpeg','image/png','image/webp')", name='mime'),
    )
    uploader_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    purpose: Mapped[str] = mapped_column(Text)
    object_key: Mapped[str] = mapped_column(Text, unique=True)
    content_type: Mapped[str] = mapped_column(Text)
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    unattached_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class PhotoAttachment(Base):
    __tablename__ = "photo_attachments"
    __table_args__ = (
        CheckConstraint('(drop_off_version_id IS NULL AND display_order IS NOT NULL AND display_order >= 0) OR (drop_off_version_id IS NOT NULL AND display_order IS NULL)', name='placement'),
        UniqueConstraint('drop_off_version_id'),
        ForeignKeyConstraint(["drop_off_version_id", "item_id"], ["drop_off_versions.id", "drop_off_versions.item_id"], ondelete="CASCADE"),
    )
    photo_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("photos.id", ondelete="RESTRICT"), primary_key=True)
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("found_items.id", ondelete="CASCADE"))
    drop_off_version_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    alt_text: Mapped[str] = mapped_column(String(200))
    display_order: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sensitive_latched: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    attached_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    detached_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class PhotoAccessGrant(UUIDPrimaryKey, Base):
    __tablename__ = "photo_access_grants"
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    photo_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("photos.id", ondelete="CASCADE"))
    session_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("sessions.id", ondelete="CASCADE"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class LostReport(UUIDPrimaryKey, Base):
    __tablename__ = "lost_reports"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','RESOLVED','CLOSED')", name='status'),
        CheckConstraint('lost_date_from <= lost_date_to', name='dates'),
        CheckConstraint("(status = 'OPEN') = (closed_at IS NULL)", name='closed_state'),
    )
    owner_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    category_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("categories.id", ondelete="RESTRICT"))
    description: Mapped[str] = mapped_column(String(2000))
    lost_date_from: Mapped[date] = mapped_column(Date)
    lost_date_to: Mapped[date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(Text, server_default='OPEN')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    version: Mapped[int] = mapped_column(BigInteger, server_default=text('1'))
    __mapper_args__ = {'version_id_col': version}

class LostReportBuilding(Base):
    __tablename__ = "lost_report_buildings"
    report_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("lost_reports.id", ondelete="CASCADE"), primary_key=True)
    building_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("buildings.id", ondelete="RESTRICT"), primary_key=True)

class LostReportPrivateDetail(Base):
    __tablename__ = "lost_report_private_details"
    report_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("lost_reports.id", ondelete="CASCADE"), primary_key=True)
    details: Mapped[str] = mapped_column(String(1000))

class MatchCandidate(UUIDPrimaryKey, Base):
    __tablename__ = "match_candidates"
    __table_args__ = (
        CheckConstraint('NOT active OR building_matched OR keyword_matched', name='reason'),
        UniqueConstraint('report_id', 'item_id'),
    )
    report_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("lost_reports.id", ondelete="CASCADE"))
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("found_items.id", ondelete="CASCADE"))
    matched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    last_evaluated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    active: Mapped[bool] = mapped_column(Boolean, server_default=text('true'))
    building_matched: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    keyword_matched: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    first_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class Collection(UUIDPrimaryKey, Base):
    __tablename__ = "collections"
    __table_args__ = (
        CheckConstraint('(undone_at IS NULL) = (undone_by_user_id IS NULL)', name='undo'),
    )
    item_id: Mapped[UUID] = mapped_column(Uuid)
    finder_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    collector_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    collected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by_user_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Dispute(UUIDPrimaryKey, Base):
    __tablename__ = "disputes"
    __table_args__ = (
        CheckConstraint("(status = 'OPEN' AND decision IS NULL AND resolved_at IS NULL AND reviewer_id IS NULL) OR (status = 'RESOLVED' AND decision IN ('UPHELD','DISMISSED') AND decision IS NOT NULL AND resolved_at IS NOT NULL AND reviewer_id IS NOT NULL)", name='review'),
    )
    collection_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("collections.id", ondelete="CASCADE"))
    reason: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(Text, server_default='OPEN')
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class CollectionRestriction(Base):
    __tablename__ = "collection_restrictions"
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True)
    restricted: Mapped[bool] = mapped_column(Boolean, server_default=text('false'))
    source_dispute_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("disputes.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class PostReport(UUIDPrimaryKey, Base):
    __tablename__ = "post_reports"
    __table_args__ = (
        CheckConstraint("reason_code IN ('INAPPROPRIATE','SPAM','OTHER')", name='reason'),
        CheckConstraint("(status = 'OPEN' AND decision IS NULL AND reviewed_at IS NULL AND reviewer_id IS NULL) OR (status = 'REVIEWED' AND decision IN ('HIDE','DISMISS') AND decision IS NOT NULL AND reviewed_at IS NOT NULL AND reviewer_id IS NOT NULL)", name='review'),
    )
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("found_items.id", ondelete="CASCADE"))
    reporter_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    reason_code: Mapped[str] = mapped_column(Text)
    details: Mapped[str] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(Text, server_default='OPEN')
    decision: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True)

class Conversation(UUIDPrimaryKey, Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint('item_id', 'member_id'),
    )
    item_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("found_items.id", ondelete="CASCADE"))
    member_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), onupdate=text("now()"))

class Message(UUIDPrimaryKey, Base):
    __tablename__ = "messages"
    conversation_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("conversations.id", ondelete="CASCADE"))
    sender_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    content: Mapped[str] = mapped_column(String(2000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class KeywordSubscription(UUIDPrimaryKey, Base):
    __tablename__ = "keyword_subscriptions"
    __table_args__ = (
        UniqueConstraint('user_id', 'normalized_keyword'),
    )
    user_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    keyword: Mapped[str] = mapped_column(String(50))
    normalized_keyword: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class OutboxEvent(UUIDPrimaryKey, Base):
    __tablename__ = "outbox_events"
    __table_args__ = (
        CheckConstraint('attempts >= 0', name='attempts'),
        UniqueConstraint('aggregate_id', 'aggregate_version', 'event_type'),
    )
    event_type: Mapped[str] = mapped_column(Text)
    aggregate_id: Mapped[UUID] = mapped_column(Uuid)
    aggregate_version: Mapped[int] = mapped_column(BigInteger)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)

class Notification(UUIDPrimaryKey, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        CheckConstraint("type IN ('MATCH_CANDIDATE','ITEM_COLLECTED','ITEM_EXPIRED','KEYWORD_MATCH')", name='type'),
        UniqueConstraint('event_id', 'recipient_id', 'type'),
    )
    event_id: Mapped[UUID] = mapped_column(Uuid)
    recipient_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    type: Mapped[str] = mapped_column(Text)
    item_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("found_items.id", ondelete="CASCADE"), nullable=True)
    report_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("lost_reports.id", ondelete="CASCADE"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class NotificationKeywordSource(Base):
    __tablename__ = "notification_keyword_sources"
    notification_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("notifications.id", ondelete="CASCADE"), primary_key=True)
    subscription_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("keyword_subscriptions.id", ondelete="CASCADE"), primary_key=True)

class EmailDelivery(UUIDPrimaryKey, Base):
    __tablename__ = "email_deliveries"
    __table_args__ = (
        CheckConstraint("(kind = 'INDIVIDUAL' AND slot_no BETWEEN 1 AND 19) OR (kind = 'DIGEST' AND slot_no = 20)", name='slot'),
        CheckConstraint("status IN ('PENDING','SENDING','SENT','RETRY','FAILED','CANCELLED')", name='status'),
        CheckConstraint('attempts >= 0', name='attempts'),
        UniqueConstraint('recipient_id', 'delivery_date', 'slot_no'),
    )
    recipient_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("users.id", ondelete="RESTRICT"))
    delivery_date: Mapped[date] = mapped_column(Date)
    kind: Mapped[str] = mapped_column(Text)
    slot_no: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(Text, server_default='PENDING')
    attempts: Mapped[int] = mapped_column(Integer, server_default=text('0'))
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

class EmailDeliveryItem(UUIDPrimaryKey, Base):
    __tablename__ = "email_delivery_items"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','QUEUED','SENT','CANCELLED')", name='status'),
    )
    notification_id: Mapped[UUID] = mapped_column(Uuid, ForeignKey("notifications.id", ondelete="CASCADE"), unique=True)
    delivery_id: Mapped[UUID | None] = mapped_column(Uuid, ForeignKey("email_deliveries.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(Text, server_default='PENDING')
    digest_on: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))

class AuditLog(UUIDPrimaryKey, Base):
    __tablename__ = "audit_logs"
    __table_args__ = (
        CheckConstraint("(actor_type = 'SYSTEM' AND actor_id IS NULL) OR (actor_type IN ('MEMBER','ADMIN') AND actor_id IS NOT NULL)", name='actor'),
        CheckConstraint("target_type IN ('FOUND_ITEM','LOST_REPORT','COLLECTION','USER','BUILDING','CATEGORY','POST_REPORT','DISPUTE')", name='target_type'),
    )
    actor_id: Mapped[UUID | None] = mapped_column(Uuid, nullable=True)
    actor_type: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[UUID] = mapped_column(Uuid)
    event_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"))
    purge_after: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AuthLoginRate(Base):
    """Short-lived, shared per-IP mock-login throttle buckets."""
    __tablename__ = 'auth_login_rates'
    ip_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    attempts: Mapped[int] = mapped_column(Integer)
