"""Daily expiry progress and backup ordering marker."""

from alembic import op
import sqlalchemy as sa


revision = '20261109_0012'
down_revision = '20261109_0011'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'daily_expiry_runs',
        sa.Column('scheduled_date', sa.Date(), primary_key=True),
        sa.Column('run_id', sa.Uuid(), nullable=False, unique=True),
        sa.Column('cutoff_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True)),
        sa.Column('last_error_code', sa.Text()),
        sa.Column('expired_items', sa.BigInteger(), nullable=False),
        sa.Column('closed_reports', sa.BigInteger(), nullable=False),
    )
    op.add_column('database_backups', sa.Column('expiry_run_id', sa.Uuid()))


def downgrade():
    op.drop_column('database_backups', 'expiry_run_id')
    op.drop_table('daily_expiry_runs')
