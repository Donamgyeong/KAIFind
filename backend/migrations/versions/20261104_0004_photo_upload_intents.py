"""Durable photo upload recovery and protection at link issuance."""
from alembic import op
import sqlalchemy as sa

revision = '20261104_0004'
down_revision = '20261103_0003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('photo_access_grants', sa.Column('requires_session', sa.Boolean(),
                                                 nullable=False, server_default=sa.true()))
    op.create_table('photo_upload_intents',
        sa.Column('object_key', sa.Text(), primary_key=True),
        sa.Column('cleanup_after', sa.DateTime(timezone=True), nullable=False))
    op.create_index('ix_photo_upload_intents_cleanup_after', 'photo_upload_intents', ['cleanup_after'])


def downgrade():
    op.drop_table('photo_upload_intents')
    op.drop_column('photo_access_grants', 'requires_session')
