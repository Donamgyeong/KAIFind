"""Prepare matching metadata; fixed-dimension vectors await model selection."""

from alembic import op
import sqlalchemy as sa


revision = '20261106_0005'
down_revision = '20261104_0004'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('found_items', 'lost_reports'):
        op.add_column(table, sa.Column(
            'description_version', sa.BigInteger(), nullable=False,
            server_default=sa.text('1'),
        ))
        op.create_check_constraint(
            op.f(f'ck_{table}_description_version_positive'), table,
            'description_version > 0',
        )

    op.execute('''
        CREATE FUNCTION advance_description_version() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.description IS DISTINCT FROM OLD.description THEN
                NEW.description_version := OLD.description_version + 1;
            ELSE
                NEW.description_version := OLD.description_version;
            END IF;
            RETURN NEW;
        END;
        $$
    ''')
    for table in ('found_items', 'lost_reports'):
        op.execute(f'''
            CREATE TRIGGER trg_{table}_description_version
            BEFORE UPDATE ON {table}
            FOR EACH ROW EXECUTE FUNCTION advance_description_version()
        ''')

    op.add_column('outbox_events', sa.Column('lease_token', sa.Uuid(), nullable=True))

    op.add_column('match_candidates', sa.Column(
        'semantic_matched', sa.Boolean(), nullable=False, server_default=sa.false(),
    ))
    op.add_column('match_candidates', sa.Column('semantic_score', sa.Double(), nullable=True))
    op.add_column('match_candidates', sa.Column('matching_policy_version', sa.Text(), nullable=True))
    for column in (
        'item_description_version', 'report_description_version',
        'item_version', 'report_version',
    ):
        op.add_column('match_candidates', sa.Column(column, sa.BigInteger(), nullable=True))

    # Preserve legacy evidence/timestamps, but do not treat keyword hits as semantic hits.
    op.drop_constraint(op.f('ck_match_candidates_reason'), 'match_candidates', type_='check')
    op.execute('''
        UPDATE match_candidates
        SET active = false
        WHERE active AND NOT building_matched
    ''')
    op.create_check_constraint(
        op.f('ck_match_candidates_reason'), 'match_candidates',
        'NOT active OR building_matched OR semantic_matched',
    )
    op.create_check_constraint(
        op.f('ck_match_candidates_semantic_score_range'), 'match_candidates',
        'semantic_score IS NULL OR semantic_score BETWEEN -1 AND 1',
    )
    op.create_check_constraint(
        op.f('ck_match_candidates_semantic_evidence'), 'match_candidates',
        'NOT semantic_matched OR (semantic_score IS NOT NULL '
        'AND item_description_version IS NOT NULL '
        'AND report_description_version IS NOT NULL)',
    )
    op.create_check_constraint(
        op.f('ck_match_candidates_evaluated_versions_positive'), 'match_candidates',
        '(item_description_version IS NULL OR item_description_version > 0) '
        'AND (report_description_version IS NULL OR report_description_version > 0) '
        'AND (item_version IS NULL OR item_version > 0) '
        'AND (report_version IS NULL OR report_version > 0)',
    )


def downgrade():
    for name in (
        'evaluated_versions_positive', 'semantic_evidence',
        'semantic_score_range', 'reason',
    ):
        op.drop_constraint(op.f(f'ck_match_candidates_{name}'), 'match_candidates', type_='check')

    # Semantic-only candidates cannot remain active under the previous contract.
    op.execute('''
        UPDATE match_candidates SET active = false
        WHERE active AND NOT building_matched AND NOT keyword_matched
    ''')
    op.create_check_constraint(
        op.f('ck_match_candidates_reason'), 'match_candidates',
        'NOT active OR building_matched OR keyword_matched',
    )
    for column in (
        'report_version', 'item_version', 'report_description_version',
        'item_description_version', 'matching_policy_version',
        'semantic_score', 'semantic_matched',
    ):
        op.drop_column('match_candidates', column)
    op.drop_column('outbox_events', 'lease_token')

    for table in ('found_items', 'lost_reports'):
        op.execute(f'DROP TRIGGER trg_{table}_description_version ON {table}')
        op.drop_constraint(
            op.f(f'ck_{table}_description_version_positive'), table, type_='check',
        )
        op.drop_column(table, 'description_version')
    op.execute('DROP FUNCTION advance_description_version()')
