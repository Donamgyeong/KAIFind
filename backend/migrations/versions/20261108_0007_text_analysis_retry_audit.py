"""Allow audited manual analysis retries without changing existing records.

Revision ID: 20261108_0007
Revises: 20261107_0006
"""
from alembic import op
import sqlalchemy as sa


revision = '20261108_0007'
down_revision = '20261107_0006'
branch_labels = None
depends_on = None

ACTIONS = (
    'ITEM_STATUS_CHANGED', 'COLLECTION_MARKED', 'COLLECTION_UNDONE', 'DROP_OFF_CHANGED',
    'SENSITIVE_PHOTO_VIEWED', 'SENSITIVE_DROP_OFF_VIEWED', 'LOST_REPORT_STATUS_CHANGED',
    'PHOTO_ACCESS_URL_ISSUED', 'ROLE_CHANGED', 'REFERENCE_CREATED', 'REFERENCE_UPDATED',
    'POST_HIDDEN', 'POST_REPORT_REVIEWED', 'DISPUTE_REVIEWED', 'COLLECTION_RESTRICTION_CHANGED',
)


def replace_constraint(actions):
    op.drop_constraint(op.f('ck_audit_logs_action'), 'audit_logs', type_='check')
    values = ','.join("'" + action + "'" for action in actions)
    op.create_check_constraint(op.f('ck_audit_logs_action'), 'audit_logs', f'action IN ({values})')


def upgrade():
    replace_constraint((*ACTIONS, 'TEXT_ANALYSIS_RETRIED'))
    replace_metadata(include_event=True)


def replace_metadata(*, include_event):
    op.drop_constraint(op.f('ck_audit_logs_metadata_keys'), 'audit_logs', type_='check')
    keys = "'fromStatus','toStatus','collectionId','photoId','reportId','disputeId','fromRole','toRole','restricted','decision'"
    if include_event:
        keys += ",'eventId'"
    op.create_check_constraint(op.f('ck_audit_logs_metadata_keys'), 'audit_logs',
        f"jsonb_typeof(metadata) = 'object' AND metadata - ARRAY[{keys}]::text[] = '{{}}'::jsonb")


def downgrade():
    # Never silently delete or relabel operational history to fit an old schema.
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM audit_logs WHERE action='TEXT_ANALYSIS_RETRIED')"
    )):
        raise RuntimeError('Retry audit history prevents downgrade; retain this revision')
    replace_constraint(ACTIONS)
    replace_metadata(include_event=False)
