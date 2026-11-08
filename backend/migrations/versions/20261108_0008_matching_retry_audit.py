"""Permit audited matching retries, retaining all prior audit history."""
from alembic import op
import sqlalchemy as sa


revision = '20261108_0008'
down_revision = '20261108_0007'
branch_labels = None
depends_on = None

ACTIONS = (
    'ITEM_STATUS_CHANGED', 'COLLECTION_MARKED', 'COLLECTION_UNDONE', 'DROP_OFF_CHANGED',
    'SENSITIVE_PHOTO_VIEWED', 'SENSITIVE_DROP_OFF_VIEWED', 'LOST_REPORT_STATUS_CHANGED',
    'PHOTO_ACCESS_URL_ISSUED', 'ROLE_CHANGED', 'REFERENCE_CREATED', 'REFERENCE_UPDATED',
    'POST_HIDDEN', 'POST_REPORT_REVIEWED', 'DISPUTE_REVIEWED', 'COLLECTION_RESTRICTION_CHANGED',
    'TEXT_ANALYSIS_RETRIED',
)


def replace(actions):
    op.drop_constraint(op.f('ck_audit_logs_action'), 'audit_logs', type_='check')
    values = ','.join("'" + action + "'" for action in actions)
    op.create_check_constraint(op.f('ck_audit_logs_action'), 'audit_logs', f'action IN ({values})')


def upgrade():
    replace((*ACTIONS, 'MATCH_EVALUATION_RETRIED'))


def downgrade():
    if op.get_bind().scalar(sa.text(
        "SELECT EXISTS (SELECT 1 FROM audit_logs WHERE action='MATCH_EVALUATION_RETRIED')"
    )):
        raise RuntimeError('Matching retry audit history prevents downgrade; retain this revision')
    replace(ACTIONS)
