"""initial KAIFind schema

Revision ID: 20261102_0001
Revises: 
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261102_0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Tables and indexes are frozen here; never import current ORM models.
    op.create_table('audit_logs',
    sa.Column('actor_id', sa.Uuid(), nullable=True),
    sa.Column('actor_type', sa.Text(), nullable=False),
    sa.Column('action', sa.Text(), nullable=False),
    sa.Column('target_type', sa.Text(), nullable=False),
    sa.Column('target_id', sa.Uuid(), nullable=False),
    sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(actor_type = 'SYSTEM' AND actor_id IS NULL) OR (actor_type IN ('MEMBER','ADMIN') AND actor_id IS NOT NULL)", name=op.f('ck_audit_logs_actor')),
    sa.CheckConstraint("action IN ('ITEM_STATUS_CHANGED','COLLECTION_MARKED','COLLECTION_UNDONE','DROP_OFF_CHANGED','SENSITIVE_PHOTO_VIEWED','SENSITIVE_DROP_OFF_VIEWED','LOST_REPORT_STATUS_CHANGED','PHOTO_ACCESS_URL_ISSUED','ROLE_CHANGED','REFERENCE_CREATED','REFERENCE_UPDATED','POST_HIDDEN','POST_REPORT_REVIEWED','DISPUTE_REVIEWED','COLLECTION_RESTRICTION_CHANGED')", name=op.f('ck_audit_logs_action')),
    sa.CheckConstraint("jsonb_typeof(metadata) = 'object' AND metadata - ARRAY['fromStatus','toStatus','collectionId','photoId','reportId','disputeId','fromRole','toRole','restricted','decision']::text[] = '{}'::jsonb", name=op.f('ck_audit_logs_metadata_keys')),
    sa.CheckConstraint("target_type IN ('FOUND_ITEM','LOST_REPORT','COLLECTION','USER','BUILDING','CATEGORY','POST_REPORT','DISPUTE')", name=op.f('ck_audit_logs_target_type')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_logs'))
    )
    op.create_index('ix_audit_logs_actor', 'audit_logs', ['actor_id', sa.literal_column('occurred_at DESC')], unique=False, postgresql_where=None)
    op.create_index('ix_audit_logs_purge', 'audit_logs', ['purge_after'], unique=False)
    op.create_index('ix_audit_logs_target', 'audit_logs', ['target_id', sa.literal_column('occurred_at DESC')], unique=False, postgresql_where=None)
    op.create_index('ix_audit_logs_time', 'audit_logs', [sa.literal_column('occurred_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_table('buildings',
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('name_ko', sa.Text(), nullable=False),
    sa.Column('name_en', sa.Text(), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_buildings')),
    sa.UniqueConstraint('code', name=op.f('uq_buildings_code'))
    )
    op.create_table('categories',
    sa.Column('name_ko', sa.Text(), nullable=False),
    sa.Column('name_en', sa.Text(), nullable=False),
    sa.Column('sensitive', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_categories'))
    )
    op.create_table('outbox_events',
    sa.Column('event_type', sa.Text(), nullable=False),
    sa.Column('aggregate_id', sa.Uuid(), nullable=False),
    sa.Column('aggregate_version', sa.BigInteger(), nullable=False),
    sa.Column('payload', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('last_error_code', sa.Text(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_outbox_events_attempts')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_outbox_events')),
    sa.UniqueConstraint('aggregate_id', 'aggregate_version', 'event_type', name=op.f('uq_outbox_events_aggregate_id'))
    )
    op.create_index('ix_outbox_events_pending', 'outbox_events', ['next_attempt_at', 'id'], unique=False, postgresql_where=sa.text('processed_at IS NULL'))
    op.create_table('users',
    sa.Column('mock_subject', sa.Text(), nullable=False),
    sa.Column('name', sa.Text(), nullable=False),
    sa.Column('email', sa.Text(), nullable=False),
    sa.Column('affiliation', sa.Text(), nullable=False),
    sa.Column('role', sa.Text(), server_default='MEMBER', nullable=False),
    sa.Column('language', sa.Text(), server_default='ko', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('version', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("affiliation IN ('STUDENT','FACULTY','STAFF')", name=op.f('ck_users_affiliation')),
    sa.CheckConstraint("language IN ('ko','en')", name=op.f('ck_users_language')),
    sa.CheckConstraint("role IN ('MEMBER','ADMIN')", name=op.f('ck_users_role')),
    sa.CheckConstraint('version > 0', name=op.f('ck_users_version_positive')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('mock_subject', name=op.f('uq_users_mock_subject'))
    )
    op.create_table('collections',
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('finder_id', sa.Uuid(), nullable=False),
    sa.Column('collector_id', sa.Uuid(), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('undone_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('undone_by_user_id', sa.Uuid(), nullable=True),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('(undone_at IS NULL) = (undone_by_user_id IS NULL)', name=op.f('ck_collections_undo')),
    sa.ForeignKeyConstraint(['collector_id'], ['users.id'], name=op.f('fk_collections_collector_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['finder_id'], ['users.id'], name=op.f('fk_collections_finder_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['undone_by_user_id'], ['users.id'], name=op.f('fk_collections_undone_by_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_collections'))
    )
    op.create_index('ix_collections_purge', 'collections', ['purge_after'], unique=False)
    op.create_index('uq_collections_active_item', 'collections', ['item_id'], unique=True, postgresql_where=sa.text('undone_at IS NULL'))
    op.create_table('email_deliveries',
    sa.Column('recipient_id', sa.Uuid(), nullable=False),
    sa.Column('delivery_date', sa.Date(), nullable=False),
    sa.Column('kind', sa.Text(), nullable=False),
    sa.Column('slot_no', sa.Integer(), nullable=False),
    sa.Column('status', sa.Text(), server_default='PENDING', nullable=False),
    sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
    sa.Column('provider_message_id', sa.Text(), nullable=True),
    sa.Column('last_error_code', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(kind = 'INDIVIDUAL' AND slot_no BETWEEN 1 AND 19) OR (kind = 'DIGEST' AND slot_no = 20)", name=op.f('ck_email_deliveries_slot')),
    sa.CheckConstraint("status IN ('PENDING','SENDING','SENT','RETRY','FAILED','CANCELLED')", name=op.f('ck_email_deliveries_status')),
    sa.CheckConstraint('attempts >= 0', name=op.f('ck_email_deliveries_attempts')),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], name=op.f('fk_email_deliveries_recipient_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_deliveries')),
    sa.UniqueConstraint('recipient_id', 'delivery_date', 'slot_no', name=op.f('uq_email_deliveries_recipient_id'))
    )
    op.create_index('ix_email_deliveries_pending', 'email_deliveries', ['next_attempt_at', 'id'], unique=False, postgresql_where=sa.text("status IN ('PENDING','RETRY')"))
    op.create_table('found_items',
    sa.Column('finder_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.Column('found_building_id', sa.Uuid(), nullable=False),
    sa.Column('title', sa.String(length=100), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=False),
    sa.Column('found_location_description', sa.String(length=300), nullable=False),
    sa.Column('found_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('status', sa.Text(), server_default='POSTED', nullable=False),
    sa.Column('hidden', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('posted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(status = 'POSTED') = (closed_at IS NULL)", name=op.f('ck_found_items_closed_state')),
    sa.CheckConstraint("status IN ('POSTED','COLLECTED','EXPIRED')", name=op.f('ck_found_items_status')),
    sa.CheckConstraint('length(btrim(description)) > 0', name=op.f('ck_found_items_description_nonblank')),
    sa.CheckConstraint('length(btrim(found_location_description)) > 0', name=op.f('ck_found_items_found_location_description_nonblank')),
    sa.CheckConstraint('length(btrim(title)) > 0', name=op.f('ck_found_items_title_nonblank')),
    sa.CheckConstraint('version > 0', name=op.f('ck_found_items_version_positive')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_found_items_category_id_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['finder_id'], ['users.id'], name=op.f('fk_found_items_finder_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['found_building_id'], ['buildings.id'], name=op.f('fk_found_items_found_building_id_buildings'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_found_items'))
    )
    op.create_index('ix_found_items_expiry', 'found_items', ['expires_at', 'id'], unique=False, postgresql_where=sa.text("status = 'POSTED' AND deleted_at IS NULL"))
    op.create_index('ix_found_items_match', 'found_items', ['category_id', 'found_building_id', 'found_at'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_found_items_owner', 'found_items', ['finder_id', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.create_index('ix_found_items_public_list', 'found_items', ['status', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=sa.text('NOT hidden AND deleted_at IS NULL'))
    op.create_index('ix_found_items_purge', 'found_items', ['purge_after'], unique=False)
    op.create_table('keyword_subscriptions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('keyword', sa.String(length=50), nullable=False),
    sa.Column('normalized_keyword', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('length(btrim(keyword)) > 0', name=op.f('ck_keyword_subscriptions_keyword_nonblank')),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_keyword_subscriptions_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_keyword_subscriptions')),
    sa.UniqueConstraint('user_id', 'normalized_keyword', name=op.f('uq_keyword_subscriptions_user_id'))
    )
    op.create_table('lost_reports',
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.Column('category_id', sa.Uuid(), nullable=False),
    sa.Column('description', sa.String(length=2000), nullable=False),
    sa.Column('lost_date_from', sa.Date(), nullable=False),
    sa.Column('lost_date_to', sa.Date(), nullable=False),
    sa.Column('status', sa.Text(), server_default='OPEN', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=True),
    sa.Column('version', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(status = 'OPEN') = (closed_at IS NULL)", name=op.f('ck_lost_reports_closed_state')),
    sa.CheckConstraint("status IN ('OPEN','RESOLVED','CLOSED')", name=op.f('ck_lost_reports_status')),
    sa.CheckConstraint('length(btrim(description)) > 0', name=op.f('ck_lost_reports_description_nonblank')),
    sa.CheckConstraint('lost_date_from <= lost_date_to', name=op.f('ck_lost_reports_dates')),
    sa.CheckConstraint('version > 0', name=op.f('ck_lost_reports_version_positive')),
    sa.ForeignKeyConstraint(['category_id'], ['categories.id'], name=op.f('fk_lost_reports_category_id_categories'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['owner_id'], ['users.id'], name=op.f('fk_lost_reports_owner_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_lost_reports'))
    )
    op.create_index('ix_lost_reports_expiry', 'lost_reports', ['expires_at', 'id'], unique=False, postgresql_where=sa.text("status = 'OPEN'"))
    op.create_index('ix_lost_reports_matching', 'lost_reports', ['category_id', 'lost_date_from'], unique=False, postgresql_where=sa.text("status = 'OPEN'"))
    op.create_index('ix_lost_reports_owner', 'lost_reports', ['owner_id', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_index('ix_lost_reports_purge', 'lost_reports', ['purge_after'], unique=False)
    op.create_table('notification_settings',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('email_enabled', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('match_email', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('collection_email', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('expiry_email', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('keyword_email', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_notification_settings_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_notification_settings'))
    )
    op.create_table('photos',
    sa.Column('uploader_id', sa.Uuid(), nullable=False),
    sa.Column('purpose', sa.Text(), nullable=False),
    sa.Column('object_key', sa.Text(), nullable=False),
    sa.Column('content_type', sa.Text(), nullable=False),
    sa.Column('size_bytes', sa.BigInteger(), nullable=False),
    sa.Column('width', sa.Integer(), nullable=False),
    sa.Column('height', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('unattached_expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("content_type IN ('image/jpeg','image/png','image/webp')", name=op.f('ck_photos_mime')),
    sa.CheckConstraint("purpose IN ('ITEM','DROP_OFF')", name=op.f('ck_photos_purpose')),
    sa.CheckConstraint('width > 0 AND height > 0 AND size_bytes > 0', name=op.f('ck_photos_dimensions')),
    sa.ForeignKeyConstraint(['uploader_id'], ['users.id'], name=op.f('fk_photos_uploader_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_photos')),
    sa.UniqueConstraint('object_key', name=op.f('uq_photos_object_key'))
    )
    op.create_index('ix_photos_unattached_expiry', 'photos', ['unattached_expires_at'], unique=False, postgresql_where=sa.text('unattached_expires_at IS NOT NULL'))
    op.create_table('sessions',
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('user_id', sa.Uuid(), nullable=True),
    sa.Column('csrf_secret_ciphertext', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_activity_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('idle_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('absolute_expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_sessions_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_sessions_token_hash'))
    )
    op.create_index('ix_sessions_absolute_expiry', 'sessions', ['absolute_expires_at'], unique=False, postgresql_where=None)
    op.create_index('ix_sessions_expiry', 'sessions', ['idle_expires_at'], unique=False, postgresql_where=None)
    op.create_table('conversations',
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('member_id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_conversations_item_id_found_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['member_id'], ['users.id'], name=op.f('fk_conversations_member_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_conversations')),
    sa.UniqueConstraint('item_id', 'member_id', name=op.f('uq_conversations_item_id'))
    )
    op.create_index('ix_conversations_item', 'conversations', ['item_id', sa.literal_column('updated_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_index('ix_conversations_member', 'conversations', ['member_id', sa.literal_column('updated_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_table('disputes',
    sa.Column('collection_id', sa.Uuid(), nullable=False),
    sa.Column('reason', sa.String(length=1000), nullable=False),
    sa.Column('status', sa.Text(), server_default='OPEN', nullable=False),
    sa.Column('decision', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewer_id', sa.Uuid(), nullable=True),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(status = 'OPEN' AND decision IS NULL AND resolved_at IS NULL AND reviewer_id IS NULL) OR (status = 'RESOLVED' AND decision IN ('UPHELD','DISMISSED') AND decision IS NOT NULL AND resolved_at IS NOT NULL AND reviewer_id IS NOT NULL)", name=op.f('ck_disputes_review')),
    sa.CheckConstraint('length(btrim(reason)) > 0', name=op.f('ck_disputes_reason_nonblank')),
    sa.ForeignKeyConstraint(['collection_id'], ['collections.id'], name=op.f('fk_disputes_collection_id_collections'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_disputes_reviewer_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_disputes'))
    )
    op.create_index('ix_disputes_purge', 'disputes', ['purge_after'], unique=False)
    op.create_index('ix_disputes_review', 'disputes', ['status', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_index('uq_disputes_open_collection', 'disputes', ['collection_id'], unique=True, postgresql_where=sa.text("status = 'OPEN'"))
    op.create_table('drop_off_versions',
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('revision_no', sa.Integer(), nullable=False),
    sa.Column('mode', sa.Text(), nullable=False),
    sa.Column('building_id', sa.Uuid(), nullable=True),
    sa.Column('spot_description', sa.String(length=300), nullable=True),
    sa.Column('changed_by_user_id', sa.Uuid(), nullable=False),
    sa.Column('changed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('sensitive_latched', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(mode = 'DROP_OFF' AND building_id IS NOT NULL AND spot_description IS NOT NULL) OR (mode = 'KEPT_BY_FINDER' AND building_id IS NULL AND spot_description IS NULL)", name=op.f('ck_drop_off_versions_location')),
    sa.CheckConstraint('length(btrim(spot_description)) > 0', name=op.f('ck_drop_off_versions_spot_description_nonblank')),
    sa.CheckConstraint('revision_no > 0', name=op.f('ck_drop_off_versions_revision')),
    sa.ForeignKeyConstraint(['building_id'], ['buildings.id'], name=op.f('fk_drop_off_versions_building_id_buildings'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], name=op.f('fk_drop_off_versions_changed_by_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_drop_off_versions_item_id_found_items'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_drop_off_versions')),
    sa.UniqueConstraint('id', 'item_id', name=op.f('uq_drop_off_versions_id')),
    sa.UniqueConstraint('item_id', 'revision_no', name=op.f('uq_drop_off_versions_item_id'))
    )
    op.create_index('ix_drop_off_versions_building', 'drop_off_versions', ['building_id', 'item_id'], unique=False, postgresql_where=None)
    op.create_index('ix_drop_off_versions_latest', 'drop_off_versions', ['item_id', sa.literal_column('revision_no DESC')], unique=False, postgresql_where=None)
    op.create_table('lost_report_buildings',
    sa.Column('report_id', sa.Uuid(), nullable=False),
    sa.Column('building_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['building_id'], ['buildings.id'], name=op.f('fk_lost_report_buildings_building_id_buildings'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['report_id'], ['lost_reports.id'], name=op.f('fk_lost_report_buildings_report_id_lost_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('report_id', 'building_id', name=op.f('pk_lost_report_buildings'))
    )
    op.create_index('ix_lost_report_buildings_reverse', 'lost_report_buildings', ['building_id', 'report_id'], unique=False, postgresql_where=None)
    op.create_table('lost_report_private_details',
    sa.Column('report_id', sa.Uuid(), nullable=False),
    sa.Column('details', sa.String(length=1000), nullable=False),
    sa.CheckConstraint('length(btrim(details)) > 0', name=op.f('ck_lost_report_private_details_details_nonblank')),
    sa.ForeignKeyConstraint(['report_id'], ['lost_reports.id'], name=op.f('fk_lost_report_private_details_report_id_lost_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('report_id', name=op.f('pk_lost_report_private_details'))
    )
    op.create_table('match_candidates',
    sa.Column('report_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('matched_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('last_evaluated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('active', sa.Boolean(), server_default=sa.text('true'), nullable=False),
    sa.Column('building_matched', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('keyword_matched', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('first_notified_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('NOT active OR building_matched OR keyword_matched', name=op.f('ck_match_candidates_reason')),
    sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_match_candidates_item_id_found_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['report_id'], ['lost_reports.id'], name=op.f('fk_match_candidates_report_id_lost_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_match_candidates')),
    sa.UniqueConstraint('report_id', 'item_id', name=op.f('uq_match_candidates_report_id'))
    )
    op.create_index('ix_match_candidates_item', 'match_candidates', ['item_id', 'report_id'], unique=False, postgresql_where=sa.text('active'))
    op.create_index('ix_match_candidates_list', 'match_candidates', ['report_id', sa.literal_column('matched_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=sa.text('active'))
    op.create_table('notifications',
    sa.Column('event_id', sa.Uuid(), nullable=False),
    sa.Column('recipient_id', sa.Uuid(), nullable=False),
    sa.Column('type', sa.Text(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=True),
    sa.Column('report_id', sa.Uuid(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('purge_after', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("type IN ('MATCH_CANDIDATE','ITEM_COLLECTED','ITEM_EXPIRED','KEYWORD_MATCH')", name=op.f('ck_notifications_type')),
    sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_notifications_item_id_found_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['recipient_id'], ['users.id'], name=op.f('fk_notifications_recipient_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['report_id'], ['lost_reports.id'], name=op.f('fk_notifications_report_id_lost_reports'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_notifications')),
    sa.UniqueConstraint('event_id', 'recipient_id', 'type', name=op.f('uq_notifications_event_id'))
    )
    op.create_index('ix_notifications_list', 'notifications', ['recipient_id', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_index('ix_notifications_purge', 'notifications', ['purge_after'], unique=False)
    op.create_index('ix_notifications_unread', 'notifications', ['recipient_id', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=sa.text('read_at IS NULL'))
    op.create_table('photo_access_grants',
    sa.Column('token_hash', sa.Text(), nullable=False),
    sa.Column('photo_id', sa.Uuid(), nullable=False),
    sa.Column('session_id', sa.Uuid(), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], name=op.f('fk_photo_access_grants_photo_id_photos'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['session_id'], ['sessions.id'], name=op.f('fk_photo_access_grants_session_id_sessions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_photo_access_grants')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_photo_access_grants_token_hash'))
    )
    op.create_index('ix_photo_access_grants_expiry', 'photo_access_grants', ['expires_at'], unique=False, postgresql_where=None)
    op.create_table('post_reports',
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('reporter_id', sa.Uuid(), nullable=False),
    sa.Column('reason_code', sa.Text(), nullable=False),
    sa.Column('details', sa.String(length=1000), nullable=False),
    sa.Column('status', sa.Text(), server_default='OPEN', nullable=False),
    sa.Column('decision', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('reviewer_id', sa.Uuid(), nullable=True),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("(status = 'OPEN' AND decision IS NULL AND reviewed_at IS NULL AND reviewer_id IS NULL) OR (status = 'REVIEWED' AND decision IN ('HIDE','DISMISS') AND decision IS NOT NULL AND reviewed_at IS NOT NULL AND reviewer_id IS NOT NULL)", name=op.f('ck_post_reports_review')),
    sa.CheckConstraint("reason_code IN ('INAPPROPRIATE','SPAM','OTHER')", name=op.f('ck_post_reports_reason')),
    sa.CheckConstraint('length(btrim(details)) > 0', name=op.f('ck_post_reports_details_nonblank')),
    sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_post_reports_item_id_found_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['reporter_id'], ['users.id'], name=op.f('fk_post_reports_reporter_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['reviewer_id'], ['users.id'], name=op.f('fk_post_reports_reviewer_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_post_reports'))
    )
    op.create_index('ix_post_reports_review', 'post_reports', ['status', sa.literal_column('created_at DESC'), sa.literal_column('id DESC')], unique=False, postgresql_where=None)
    op.create_index('uq_post_reports_open_reporter', 'post_reports', ['item_id', 'reporter_id'], unique=True, postgresql_where=sa.text("status = 'OPEN'"))
    op.create_table('collection_restrictions',
    sa.Column('user_id', sa.Uuid(), nullable=False),
    sa.Column('restricted', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('source_dispute_id', sa.Uuid(), nullable=True),
    sa.Column('updated_by_user_id', sa.Uuid(), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['source_dispute_id'], ['disputes.id'], name=op.f('fk_collection_restrictions_source_dispute_id_disputes'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['updated_by_user_id'], ['users.id'], name=op.f('fk_collection_restrictions_updated_by_user_id_users'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_collection_restrictions_user_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('user_id', name=op.f('pk_collection_restrictions'))
    )
    op.create_table('email_delivery_items',
    sa.Column('notification_id', sa.Uuid(), nullable=False),
    sa.Column('delivery_id', sa.Uuid(), nullable=True),
    sa.Column('status', sa.Text(), server_default='PENDING', nullable=False),
    sa.Column('digest_on', sa.Date(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint("status IN ('PENDING','QUEUED','SENT','CANCELLED')", name=op.f('ck_email_delivery_items_status')),
    sa.ForeignKeyConstraint(['delivery_id'], ['email_deliveries.id'], name=op.f('fk_email_delivery_items_delivery_id_email_deliveries'), ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], name=op.f('fk_email_delivery_items_notification_id_notifications'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_email_delivery_items')),
    sa.UniqueConstraint('notification_id', name=op.f('uq_email_delivery_items_notification_id'))
    )
    op.create_table('messages',
    sa.Column('conversation_id', sa.Uuid(), nullable=False),
    sa.Column('sender_id', sa.Uuid(), nullable=False),
    sa.Column('content', sa.String(length=2000), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('length(btrim(content)) > 0', name=op.f('ck_messages_content_nonblank')),
    sa.ForeignKeyConstraint(['conversation_id'], ['conversations.id'], name=op.f('fk_messages_conversation_id_conversations'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['sender_id'], ['users.id'], name=op.f('fk_messages_sender_id_users'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_messages'))
    )
    op.create_index('ix_messages_conversation', 'messages', ['conversation_id', 'created_at', 'id'], unique=False, postgresql_where=None)
    op.create_table('notification_keyword_sources',
    sa.Column('notification_id', sa.Uuid(), nullable=False),
    sa.Column('subscription_id', sa.Uuid(), nullable=False),
    sa.ForeignKeyConstraint(['notification_id'], ['notifications.id'], name=op.f('fk_notification_keyword_sources_notification_id_notifications'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['subscription_id'], ['keyword_subscriptions.id'], name=op.f('fk_notification_keyword_sources_subscription_id_keyword_subscriptions'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('notification_id', 'subscription_id', name=op.f('pk_notification_keyword_sources'))
    )
    op.create_table('photo_attachments',
    sa.Column('photo_id', sa.Uuid(), nullable=False),
    sa.Column('item_id', sa.Uuid(), nullable=False),
    sa.Column('drop_off_version_id', sa.Uuid(), nullable=True),
    sa.Column('alt_text', sa.String(length=200), nullable=False),
    sa.Column('display_order', sa.Integer(), nullable=True),
    sa.Column('sensitive_latched', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('attached_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.Column('detached_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint('(drop_off_version_id IS NULL AND display_order IS NOT NULL AND display_order >= 0) OR (drop_off_version_id IS NOT NULL AND display_order IS NULL)', name=op.f('ck_photo_attachments_placement')),
    sa.CheckConstraint('length(btrim(alt_text)) > 0', name=op.f('ck_photo_attachments_alt_text_nonblank')),
    sa.ForeignKeyConstraint(['drop_off_version_id', 'item_id'], ['drop_off_versions.id', 'drop_off_versions.item_id'], name=op.f('fk_photo_attachments_drop_off_version_id_drop_off_versions'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_photo_attachments_item_id_found_items'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['photo_id'], ['photos.id'], name=op.f('fk_photo_attachments_photo_id_photos'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('photo_id', name=op.f('pk_photo_attachments')),
    sa.UniqueConstraint('drop_off_version_id', name=op.f('uq_photo_attachments_drop_off_version_id'))
    )
    op.create_index('uq_photo_attachments_active_order', 'photo_attachments', ['item_id', 'display_order'], unique=True, postgresql_where=sa.text('detached_at IS NULL AND drop_off_version_id IS NULL'))
    # End schema operations.
    for statement in GUARD_STATEMENTS:
        op.execute(statement)


def downgrade():
    # Tables and indexes are frozen here; never import current ORM models.
    op.drop_index('uq_photo_attachments_active_order', table_name='photo_attachments', postgresql_where=sa.text('detached_at IS NULL AND drop_off_version_id IS NULL'))
    op.drop_table('photo_attachments')
    op.drop_table('notification_keyword_sources')
    op.drop_index('ix_messages_conversation', table_name='messages', postgresql_where=None)
    op.drop_table('messages')
    op.drop_table('email_delivery_items')
    op.drop_table('collection_restrictions')
    op.drop_index('uq_post_reports_open_reporter', table_name='post_reports', postgresql_where=sa.text("status = 'OPEN'"))
    op.drop_index('ix_post_reports_review', table_name='post_reports', postgresql_where=None)
    op.drop_table('post_reports')
    op.drop_index('ix_photo_access_grants_expiry', table_name='photo_access_grants', postgresql_where=None)
    op.drop_table('photo_access_grants')
    op.drop_index('ix_notifications_unread', table_name='notifications', postgresql_where=sa.text('read_at IS NULL'))
    op.drop_index('ix_notifications_purge', table_name='notifications')
    op.drop_index('ix_notifications_list', table_name='notifications', postgresql_where=None)
    op.drop_table('notifications')
    op.drop_index('ix_match_candidates_list', table_name='match_candidates', postgresql_where=sa.text('active'))
    op.drop_index('ix_match_candidates_item', table_name='match_candidates', postgresql_where=sa.text('active'))
    op.drop_table('match_candidates')
    op.drop_table('lost_report_private_details')
    op.drop_index('ix_lost_report_buildings_reverse', table_name='lost_report_buildings', postgresql_where=None)
    op.drop_table('lost_report_buildings')
    op.drop_index('ix_drop_off_versions_latest', table_name='drop_off_versions', postgresql_where=None)
    op.drop_index('ix_drop_off_versions_building', table_name='drop_off_versions', postgresql_where=None)
    op.drop_table('drop_off_versions')
    op.drop_index('uq_disputes_open_collection', table_name='disputes', postgresql_where=sa.text("status = 'OPEN'"))
    op.drop_index('ix_disputes_review', table_name='disputes', postgresql_where=None)
    op.drop_index('ix_disputes_purge', table_name='disputes')
    op.drop_table('disputes')
    op.drop_index('ix_conversations_member', table_name='conversations', postgresql_where=None)
    op.drop_index('ix_conversations_item', table_name='conversations', postgresql_where=None)
    op.drop_table('conversations')
    op.drop_index('ix_sessions_expiry', table_name='sessions', postgresql_where=None)
    op.drop_index('ix_sessions_absolute_expiry', table_name='sessions', postgresql_where=None)
    op.drop_table('sessions')
    op.drop_index('ix_photos_unattached_expiry', table_name='photos', postgresql_where=sa.text('unattached_expires_at IS NOT NULL'))
    op.drop_table('photos')
    op.drop_table('notification_settings')
    op.drop_index('ix_lost_reports_purge', table_name='lost_reports')
    op.drop_index('ix_lost_reports_owner', table_name='lost_reports', postgresql_where=None)
    op.drop_index('ix_lost_reports_matching', table_name='lost_reports', postgresql_where=sa.text("status = 'OPEN'"))
    op.drop_index('ix_lost_reports_expiry', table_name='lost_reports', postgresql_where=sa.text("status = 'OPEN'"))
    op.drop_table('lost_reports')
    op.drop_table('keyword_subscriptions')
    op.drop_index('ix_found_items_purge', table_name='found_items')
    op.drop_index('ix_found_items_public_list', table_name='found_items', postgresql_where=sa.text('NOT hidden AND deleted_at IS NULL'))
    op.drop_index('ix_found_items_owner', table_name='found_items', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_found_items_match', table_name='found_items', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_index('ix_found_items_expiry', table_name='found_items', postgresql_where=sa.text("status = 'POSTED' AND deleted_at IS NULL"))
    op.drop_table('found_items')
    op.drop_index('ix_email_deliveries_pending', table_name='email_deliveries', postgresql_where=sa.text("status IN ('PENDING','RETRY')"))
    op.drop_table('email_deliveries')
    op.drop_index('uq_collections_active_item', table_name='collections', postgresql_where=sa.text('undone_at IS NULL'))
    op.drop_index('ix_collections_purge', table_name='collections')
    op.drop_table('collections')
    op.drop_table('users')
    op.drop_index('ix_outbox_events_pending', table_name='outbox_events', postgresql_where=sa.text('processed_at IS NULL'))
    op.drop_table('outbox_events')
    op.drop_table('categories')
    op.drop_table('buildings')
    op.drop_index('ix_audit_logs_time', table_name='audit_logs', postgresql_where=None)
    op.drop_index('ix_audit_logs_target', table_name='audit_logs', postgresql_where=None)
    op.drop_index('ix_audit_logs_purge', table_name='audit_logs')
    op.drop_index('ix_audit_logs_actor', table_name='audit_logs', postgresql_where=None)
    op.drop_table('audit_logs')
    # End schema operations.
    op.execute("DROP FUNCTION kaifind_category_guard()")
    op.execute("DROP FUNCTION kaifind_lost_report_cleanup()")
    op.execute("DROP FUNCTION kaifind_private_details_guard()")
    op.execute("DROP FUNCTION kaifind_photo_attachment_guard()")
    op.execute("DROP FUNCTION kaifind_drop_off_guard()")
    op.execute("DROP FUNCTION kaifind_item_cleanup()")
    op.execute("DROP FUNCTION kaifind_conversation_guard()")
    op.execute("DROP FUNCTION kaifind_message_guard()")


# Frozen PostgreSQL lifecycle guards, deliberately independent of live ORM metadata.
GUARD_STATEMENTS = [
    """CREATE FUNCTION kaifind_category_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.sensitive IS DISTINCT FROM OLD.sensitive THEN
        RAISE EXCEPTION 'Category sensitivity is immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER category_guard BEFORE UPDATE ON categories
FOR EACH ROW EXECUTE FUNCTION kaifind_category_guard()""",
    """CREATE FUNCTION kaifind_lost_report_cleanup() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.closed_at IS NOT NULL AND
           (NEW.closed_at IS DISTINCT FROM OLD.closed_at OR NEW.status = 'OPEN') THEN
            RAISE EXCEPTION 'Closed reports cannot reopen or change closure time' USING ERRCODE = '23514';
        END IF;
    END IF;
    IF NEW.status <> 'OPEN' THEN
        DELETE FROM lost_report_private_details WHERE report_id = NEW.id;
        UPDATE email_delivery_items SET status = 'CANCELLED'
        WHERE notification_id IN (SELECT id FROM notifications WHERE report_id = NEW.id)
          AND status IN ('PENDING','QUEUED');
    END IF;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER lost_report_cleanup AFTER INSERT OR UPDATE ON lost_reports
FOR EACH ROW EXECUTE FUNCTION kaifind_lost_report_cleanup()""",
    """CREATE FUNCTION kaifind_private_details_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE rid uuid; report_status text; has_details boolean;
BEGIN
    IF TG_TABLE_NAME = 'lost_reports' THEN rid := COALESCE(NEW.id, OLD.id);
    ELSE rid := COALESCE(NEW.report_id, OLD.report_id); END IF;
    SELECT status INTO report_status FROM lost_reports WHERE id = rid FOR UPDATE;
    IF NOT FOUND THEN RETURN NULL; END IF;
    SELECT EXISTS(SELECT 1 FROM lost_report_private_details WHERE report_id = rid) INTO has_details;
    IF (report_status = 'OPEN') IS DISTINCT FROM has_details THEN
        RAISE EXCEPTION 'Only open reports must have private details' USING ERRCODE = '23514';
    END IF;
    RETURN NULL;
END $$""",
    """CREATE CONSTRAINT TRIGGER report_private_details_guard
AFTER INSERT OR UPDATE ON lost_reports DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION kaifind_private_details_guard()""",
    """CREATE CONSTRAINT TRIGGER private_details_guard
AFTER INSERT OR UPDATE OR DELETE ON lost_report_private_details DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION kaifind_private_details_guard()""",
    """CREATE FUNCTION kaifind_photo_attachment_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE photo_purpose text; photo_owner uuid; item_owner uuid; is_sensitive boolean;
BEGIN
    SELECT f.finder_id, c.sensitive INTO item_owner, is_sensitive
    FROM found_items f JOIN categories c ON c.id = f.category_id
    WHERE f.id = NEW.item_id FOR UPDATE OF f;
    SELECT purpose, uploader_id INTO photo_purpose, photo_owner
    FROM photos WHERE id = NEW.photo_id FOR UPDATE;
    IF photo_owner IS DISTINCT FROM item_owner OR
       (photo_purpose = 'ITEM') IS DISTINCT FROM (NEW.drop_off_version_id IS NULL) THEN
        RAISE EXCEPTION 'Photo ownership or purpose mismatch' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' THEN
        IF NEW.item_id IS DISTINCT FROM OLD.item_id OR NEW.photo_id IS DISTINCT FROM OLD.photo_id
           OR NEW.drop_off_version_id IS DISTINCT FROM OLD.drop_off_version_id
           OR (OLD.sensitive_latched AND NOT NEW.sensitive_latched) THEN
            RAISE EXCEPTION 'Photo attachment identity and protection cannot be reset' USING ERRCODE = '23514';
        END IF;
    END IF;
    NEW.sensitive_latched := NEW.sensitive_latched OR is_sensitive;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER photo_attachment_guard BEFORE INSERT OR UPDATE ON photo_attachments
FOR EACH ROW EXECUTE FUNCTION kaifind_photo_attachment_guard()""",
    """CREATE FUNCTION kaifind_drop_off_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE is_sensitive boolean;
BEGIN
    SELECT c.sensitive INTO is_sensitive FROM found_items f
    JOIN categories c ON c.id = f.category_id WHERE f.id = NEW.item_id FOR UPDATE OF f;
    IF TG_OP = 'UPDATE' THEN
        IF (to_jsonb(NEW) - 'sensitive_latched') IS DISTINCT FROM
           (to_jsonb(OLD) - 'sensitive_latched') OR
           (OLD.sensitive_latched AND NOT NEW.sensitive_latched) THEN
            RAISE EXCEPTION 'Drop-off history is immutable' USING ERRCODE = '23514';
        END IF;
    END IF;
    NEW.sensitive_latched := NEW.sensitive_latched OR is_sensitive;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER drop_off_guard BEFORE INSERT OR UPDATE ON drop_off_versions
FOR EACH ROW EXECUTE FUNCTION kaifind_drop_off_guard()""",
    """CREATE FUNCTION kaifind_item_cleanup() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.status <> 'POSTED' OR NEW.deleted_at IS NOT NULL THEN
        DELETE FROM conversations WHERE item_id = NEW.id;
    END IF;
    IF NEW.deleted_at IS NOT NULL THEN
        DELETE FROM match_candidates WHERE item_id = NEW.id;
    END IF;
    IF EXISTS(SELECT 1 FROM categories WHERE id = NEW.category_id AND sensitive) THEN
        UPDATE photo_attachments SET sensitive_latched = true
        WHERE item_id = NEW.id AND NOT sensitive_latched;
        UPDATE drop_off_versions SET sensitive_latched = true
        WHERE item_id = NEW.id AND NOT sensitive_latched;
    END IF;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER item_cleanup AFTER UPDATE ON found_items
FOR EACH ROW EXECUTE FUNCTION kaifind_item_cleanup()""",
    """CREATE FUNCTION kaifind_conversation_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE item_status text; item_deleted timestamptz; item_hidden boolean; finder uuid;
BEGIN
    SELECT status, deleted_at, hidden, finder_id INTO item_status, item_deleted, item_hidden, finder
    FROM found_items WHERE id = NEW.item_id FOR UPDATE;
    IF item_status IS DISTINCT FROM 'POSTED' OR item_deleted IS NOT NULL
       OR (TG_OP = 'INSERT' AND item_hidden) OR NEW.member_id = finder THEN
        RAISE EXCEPTION 'Item does not allow this conversation' USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'UPDATE' AND (NEW.item_id IS DISTINCT FROM OLD.item_id OR NEW.member_id IS DISTINCT FROM OLD.member_id) THEN
        RAISE EXCEPTION 'Conversation participants are immutable' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER conversation_guard BEFORE INSERT OR UPDATE ON conversations
FOR EACH ROW EXECUTE FUNCTION kaifind_conversation_guard()""",
    """CREATE FUNCTION kaifind_message_guard() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE target_item uuid; member uuid; finder uuid; item_status text; item_deleted timestamptz;
BEGIN
    SELECT item_id, member_id INTO target_item, member FROM conversations WHERE id = NEW.conversation_id;
    SELECT finder_id, status, deleted_at INTO finder, item_status, item_deleted
    FROM found_items WHERE id = target_item FOR UPDATE;
    IF item_status IS DISTINCT FROM 'POSTED' OR item_deleted IS NOT NULL
       OR (NEW.sender_id IS DISTINCT FROM member AND NEW.sender_id IS DISTINCT FROM finder) THEN
        RAISE EXCEPTION 'Message sender or item state is invalid' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END $$""",
    """CREATE TRIGGER message_guard BEFORE INSERT OR UPDATE ON messages
FOR EACH ROW EXECUTE FUNCTION kaifind_message_guard()""",
]
