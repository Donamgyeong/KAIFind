"""Daily PostgreSQL backup execution history."""

from alembic import op
import sqlalchemy as sa


revision = '20261109_0011'
down_revision = '20261109_0010'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'database_backups',
        sa.Column('scheduled_date', sa.Date(), primary_key=True),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True)),
        sa.Column('object_key', sa.Text()),
        sa.Column('sha256', sa.Text()),
        sa.Column('size_bytes', sa.BigInteger()),
        sa.Column('last_error_code', sa.Text()),
    )


def downgrade():
    op.drop_table('database_backups')
