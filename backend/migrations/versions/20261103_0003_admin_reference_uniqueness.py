"""Enforce normalized reference uniqueness for concurrent admin mutations.

Revision ID: 20261103_0003
Revises: 20261103_0002
"""
from alembic import op
import sqlalchemy as sa

revision = '20261103_0003'
down_revision = '20261103_0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('uq_buildings_code_normalized', 'buildings',
                    [sa.text('lower(btrim(code))')], unique=True)
    for lang in ('ko', 'en'):
        op.create_index(f'uq_categories_name_{lang}_normalized', 'categories',
                        [sa.text(f'lower(btrim(name_{lang}))')], unique=True)


def downgrade():
    for lang in ('ko', 'en'):
        op.drop_index(f'uq_categories_name_{lang}_normalized', table_name='categories')
    op.drop_index('uq_buildings_code_normalized', table_name='buildings')
