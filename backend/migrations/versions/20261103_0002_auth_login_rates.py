"""Shared mock-login rate limits.

Revision ID: 20261103_0002
Revises: 20261102_0001
"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_0002'
down_revision = '20261102_0001'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('auth_login_rates',
        sa.Column('ip_hash', sa.String(64), primary_key=True),
        sa.Column('window_started_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False))
    op.create_index('ix_auth_login_rates_window_started_at', 'auth_login_rates', ['window_started_at'])


def downgrade():
    op.drop_table('auth_login_rates')
