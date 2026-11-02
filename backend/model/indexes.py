"""Query and concurrency indexes; imported once with the model package."""
from sqlalchemy import CheckConstraint, Index, String, text
from .base import Base


def index(table, name, *columns, where=None, unique=False):
    target = Base.metadata.tables[table]
    expressions = [target.c[c[:-5]].desc() if c.endswith(' DESC') else target.c[c]
                   for c in columns]
    Index(name, *expressions, unique=unique,
          postgresql_where=text(where) if where else None)


index('collections', 'uq_collections_active_item', 'item_id', unique=True,
      where='undone_at IS NULL')
index('disputes', 'uq_disputes_open_collection', 'collection_id', unique=True,
      where="status = 'OPEN'")
index('post_reports', 'uq_post_reports_open_reporter', 'item_id', 'reporter_id',
      unique=True, where="status = 'OPEN'")
index('photo_attachments', 'uq_photo_attachments_active_order', 'item_id',
      'display_order', unique=True,
      where='detached_at IS NULL AND drop_off_version_id IS NULL')
index('found_items', 'ix_found_items_public_list', 'status', 'created_at DESC',
      'id DESC', where='NOT hidden AND deleted_at IS NULL')
index('found_items', 'ix_found_items_match', 'category_id', 'found_building_id',
      'found_at', where='deleted_at IS NULL')
index('found_items', 'ix_found_items_owner', 'finder_id', 'created_at DESC',
      'id DESC', where='deleted_at IS NULL')
index('found_items', 'ix_found_items_expiry', 'expires_at', 'id',
      where="status = 'POSTED' AND deleted_at IS NULL")
index('drop_off_versions', 'ix_drop_off_versions_latest', 'item_id', 'revision_no DESC')
index('drop_off_versions', 'ix_drop_off_versions_building', 'building_id', 'item_id')
index('lost_reports', 'ix_lost_reports_owner', 'owner_id', 'created_at DESC', 'id DESC')
index('lost_reports', 'ix_lost_reports_matching', 'category_id', 'lost_date_from',
      where="status = 'OPEN'")
index('lost_reports', 'ix_lost_reports_expiry', 'expires_at', 'id', where="status = 'OPEN'")
index('lost_report_buildings', 'ix_lost_report_buildings_reverse', 'building_id', 'report_id')
index('match_candidates', 'ix_match_candidates_list', 'report_id', 'matched_at DESC',
      'id DESC', where='active')
index('match_candidates', 'ix_match_candidates_item', 'item_id', 'report_id', where='active')
index('conversations', 'ix_conversations_member', 'member_id', 'updated_at DESC', 'id DESC')
index('conversations', 'ix_conversations_item', 'item_id', 'updated_at DESC', 'id DESC')
index('messages', 'ix_messages_conversation', 'conversation_id', 'created_at', 'id')
index('notifications', 'ix_notifications_list', 'recipient_id', 'created_at DESC', 'id DESC')
index('notifications', 'ix_notifications_unread', 'recipient_id', 'created_at DESC',
      'id DESC', where='read_at IS NULL')
index('outbox_events', 'ix_outbox_events_pending', 'next_attempt_at', 'id',
      where='processed_at IS NULL')
index('email_deliveries', 'ix_email_deliveries_pending', 'next_attempt_at', 'id',
      where="status IN ('PENDING','RETRY')")
for table in ('disputes', 'post_reports'):
    index(table, f'ix_{table}_review', 'status', 'created_at DESC', 'id DESC')
index('audit_logs', 'ix_audit_logs_time', 'occurred_at DESC', 'id DESC')
index('audit_logs', 'ix_audit_logs_target', 'target_id', 'occurred_at DESC')
index('audit_logs', 'ix_audit_logs_actor', 'actor_id', 'occurred_at DESC')
index('sessions', 'ix_sessions_expiry', 'idle_expires_at')
index('sessions', 'ix_sessions_absolute_expiry', 'absolute_expires_at')
index('photo_access_grants', 'ix_photo_access_grants_expiry', 'expires_at')
index('photos', 'ix_photos_unattached_expiry', 'unattached_expires_at',
      where='unattached_expires_at IS NOT NULL')

for table in Base.metadata.tables.values():
    if 'purge_after' in table.c:
        Index(f'ix_{table.name}_purge', table.c.purge_after)
    for column in table.c:
        if isinstance(column.type, String) and column.type.length:
            table.append_constraint(CheckConstraint(
                f'length(btrim({column.name})) > 0', name=f'{column.name}_nonblank'))
    if 'version' in table.c:
        table.append_constraint(CheckConstraint('version > 0', name='version_positive'))

_audit = Base.metadata.tables['audit_logs']
_audit.append_constraint(CheckConstraint(
    "action IN ('ITEM_STATUS_CHANGED','COLLECTION_MARKED','COLLECTION_UNDONE',"
    "'DROP_OFF_CHANGED','SENSITIVE_PHOTO_VIEWED','SENSITIVE_DROP_OFF_VIEWED',"
    "'LOST_REPORT_STATUS_CHANGED','PHOTO_ACCESS_URL_ISSUED','ROLE_CHANGED',"
    "'REFERENCE_CREATED','REFERENCE_UPDATED','POST_HIDDEN','POST_REPORT_REVIEWED',"
    "'DISPUTE_REVIEWED','COLLECTION_RESTRICTION_CHANGED')", name='action'))
_audit.append_constraint(CheckConstraint(
    "jsonb_typeof(metadata) = 'object' AND "
    "metadata - ARRAY['fromStatus','toStatus','collectionId','photoId','reportId',"
    "'disputeId','fromRole','toRole','restricted','decision']::text[] = '{}'::jsonb",
    name='metadata_keys'))
