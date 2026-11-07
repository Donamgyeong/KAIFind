"""translation_keyword_matching

Revision ID: 20261107_0006
Revises: 20261106_0005
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '20261107_0006'
down_revision = '20261106_0005'
branch_labels = None
depends_on = None


def upgrade():
    for table in ('found_items', 'lost_reports'):
        op.execute(f'DROP TRIGGER trg_{table}_description_version ON {table}')
        op.drop_constraint(op.f(f'ck_{table}_description_version_positive'), table, type_='check')
        op.alter_column(table, 'description_version', new_column_name='text_version')
    op.execute('DROP FUNCTION advance_description_version()')

    # Preserve prior semantic evidence without using it as new keyword evidence.
    op.add_column('match_candidates', sa.Column('legacy_evidence', postgresql.JSONB(), nullable=True))
    op.execute('''UPDATE match_candidates SET legacy_evidence = jsonb_build_object(
        'semantic_matched', semantic_matched, 'semantic_score', semantic_score,
        'matching_policy_version', matching_policy_version,
        'item_description_version', item_description_version,
        'report_description_version', report_description_version,
        'item_version', item_version, 'report_version', report_version, 'active', active)
    ''')
    for name in ('evaluated_versions_positive', 'semantic_evidence', 'semantic_score_range', 'reason'):
        op.drop_constraint(op.f(f'ck_match_candidates_{name}'), 'match_candidates', type_='check')
    op.execute('UPDATE match_candidates SET active = false WHERE active AND NOT building_matched')
    op.create_check_constraint(op.f('ck_match_candidates_reason'), 'match_candidates',
                               'NOT active OR building_matched OR keyword_matched')
    for column in ('semantic_matched', 'semantic_score', 'matching_policy_version',
                   'item_description_version', 'report_description_version', 'item_version', 'report_version'):
        op.drop_column('match_candidates', column)
    op.create_table('text_analysis_profiles',
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('model_name', sa.Text(), nullable=False),
        sa.Column('model_revision', sa.Text(), nullable=False),
        sa.Column('tokenizer_revision', sa.Text(), nullable=False),
        sa.Column('input_format_version', sa.Text(), nullable=False),
        sa.Column('language_rule_version', sa.Text(), nullable=False),
        sa.Column('keyword_rule_version', sa.Text(), nullable=False),
        sa.Column('runtime_config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(input_format_version) <> ''", name=op.f('ck_text_analysis_profiles_input_format_nonblank')),
        sa.CheckConstraint("btrim(keyword_rule_version) <> ''", name=op.f('ck_text_analysis_profiles_keyword_rule_nonblank')),
        sa.CheckConstraint("btrim(language_rule_version) <> ''", name=op.f('ck_text_analysis_profiles_language_rule_nonblank')),
        sa.CheckConstraint("btrim(model_name) <> ''", name=op.f('ck_text_analysis_profiles_model_name_nonblank')),
        sa.CheckConstraint("btrim(name) <> ''", name=op.f('ck_text_analysis_profiles_name_nonblank')),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name=op.f('ck_text_analysis_profiles_fingerprint_sha256')),
        sa.CheckConstraint("jsonb_typeof(runtime_config) = 'object'", name=op.f('ck_text_analysis_profiles_runtime_object')),
        sa.CheckConstraint("model_revision ~ '^[0-9a-f]{40}$'", name=op.f('ck_text_analysis_profiles_model_revision_commit')),
        sa.CheckConstraint("tokenizer_revision ~ '^[0-9a-f]{40}$'", name=op.f('ck_text_analysis_profiles_tokenizer_revision_commit')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_text_analysis_profiles')),
        sa.UniqueConstraint('fingerprint', name=op.f('uq_text_analysis_profiles_fingerprint')),
        sa.UniqueConstraint('name', name=op.f('uq_text_analysis_profiles_name'))
    )
    op.create_table('matching_policies',
        sa.Column('analysis_profile_id', sa.Uuid(), nullable=False),
        sa.Column('rule_version', sa.Text(), nullable=False),
        sa.Column('config', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('fingerprint', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.CheckConstraint("btrim(rule_version) <> ''", name=op.f('ck_matching_policies_rule_nonblank')),
        sa.CheckConstraint("fingerprint ~ '^[0-9a-f]{64}$'", name=op.f('ck_matching_policies_fingerprint_sha256')),
        sa.CheckConstraint("jsonb_typeof(config) = 'object'", name=op.f('ck_matching_policies_config_object')),
        sa.ForeignKeyConstraint(['analysis_profile_id'], ['text_analysis_profiles.id'], name=op.f('fk_matching_policies_analysis_profile_id_text_analysis_profiles'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_matching_policies')),
        sa.UniqueConstraint('fingerprint', name=op.f('uq_matching_policies_fingerprint')),
        sa.UniqueConstraint('id', 'analysis_profile_id', name='uq_matching_policies_id_profile')
    )
    op.create_table('found_item_text_features',
        sa.Column('item_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('text_version', sa.BigInteger(), nullable=False),
        sa.Column('source_hash', sa.Text(), nullable=False),
        sa.Column('source_language', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default='PENDING', nullable=False),
        sa.Column('translated_text', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_code', sa.Text(), nullable=True),
        sa.CheckConstraint("(status = 'READY' AND translated_text IS NOT NULL AND keywords IS NOT NULL AND attributes IS NOT NULL AND completed_at IS NOT NULL AND last_error_code IS NULL) OR (status <> 'READY' AND translated_text IS NULL AND keywords IS NULL AND attributes IS NULL)", name=op.f('ck_found_item_text_features_result_state')),
        sa.CheckConstraint("(status IN ('PENDING','PROCESSING') AND completed_at IS NULL AND last_error_code IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND last_error_code IS NOT NULL) OR (status IN ('READY','SUPERSEDED') AND completed_at IS NOT NULL AND last_error_code IS NULL)", name=op.f('ck_found_item_text_features_completion_state')),
        sa.CheckConstraint("attributes IS NULL OR jsonb_typeof(attributes) = 'object'", name=op.f('ck_found_item_text_features_attributes_object')),
        sa.CheckConstraint("last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'", name=op.f('ck_found_item_text_features_error_code')),
        sa.CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_found_item_text_features_source_hash_sha256')),
        sa.CheckConstraint("source_language IN ('KO','EN','MIXED')", name=op.f('ck_found_item_text_features_source_language')),
        sa.CheckConstraint("status IN ('PENDING','PROCESSING','READY','FAILED','SUPERSEDED')", name=op.f('ck_found_item_text_features_status')),
        sa.CheckConstraint('keywords IS NULL OR (coalesce(array_ndims(keywords), 1) = 1 AND array_position(keywords, NULL) IS NULL)', name=op.f('ck_found_item_text_features_keywords_shape')),
        sa.CheckConstraint('text_version > 0', name=op.f('ck_found_item_text_features_text_version_positive')),
        sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_found_item_text_features_item_id_found_items'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['profile_id'], ['text_analysis_profiles.id'], name=op.f('fk_found_item_text_features_profile_id_text_analysis_profiles'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_found_item_text_features')),
        sa.UniqueConstraint('id', 'item_id', 'profile_id', name='uq_item_id_feature_identity'),
        sa.UniqueConstraint('item_id', 'profile_id', 'text_version', name=op.f('uq_found_item_text_features_item_id'))
    )
    op.create_index('ix_found_item_text_features_backfill', 'found_item_text_features', ['profile_id', 'status', 'item_id'], unique=False, postgresql_where=None)
    op.create_table('lost_report_text_features',
        sa.Column('report_id', sa.Uuid(), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), nullable=False),
        sa.Column('text_version', sa.BigInteger(), nullable=False),
        sa.Column('source_hash', sa.Text(), nullable=False),
        sa.Column('source_language', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), server_default='PENDING', nullable=False),
        sa.Column('translated_text', sa.Text(), nullable=True),
        sa.Column('keywords', postgresql.ARRAY(sa.Text()), nullable=True),
        sa.Column('attributes', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_code', sa.Text(), nullable=True),
        sa.CheckConstraint("(status = 'READY' AND translated_text IS NOT NULL AND keywords IS NOT NULL AND attributes IS NOT NULL AND completed_at IS NOT NULL AND last_error_code IS NULL) OR (status <> 'READY' AND translated_text IS NULL AND keywords IS NULL AND attributes IS NULL)", name=op.f('ck_lost_report_text_features_result_state')),
        sa.CheckConstraint("(status IN ('PENDING','PROCESSING') AND completed_at IS NULL AND last_error_code IS NULL) OR (status = 'FAILED' AND completed_at IS NOT NULL AND last_error_code IS NOT NULL) OR (status IN ('READY','SUPERSEDED') AND completed_at IS NOT NULL AND last_error_code IS NULL)", name=op.f('ck_lost_report_text_features_completion_state')),
        sa.CheckConstraint("attributes IS NULL OR jsonb_typeof(attributes) = 'object'", name=op.f('ck_lost_report_text_features_attributes_object')),
        sa.CheckConstraint("last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'", name=op.f('ck_lost_report_text_features_error_code')),
        sa.CheckConstraint("source_hash ~ '^[0-9a-f]{64}$'", name=op.f('ck_lost_report_text_features_source_hash_sha256')),
        sa.CheckConstraint("source_language IN ('KO','EN','MIXED')", name=op.f('ck_lost_report_text_features_source_language')),
        sa.CheckConstraint("status IN ('PENDING','PROCESSING','READY','FAILED','SUPERSEDED')", name=op.f('ck_lost_report_text_features_status')),
        sa.CheckConstraint('keywords IS NULL OR (coalesce(array_ndims(keywords), 1) = 1 AND array_position(keywords, NULL) IS NULL)', name=op.f('ck_lost_report_text_features_keywords_shape')),
        sa.CheckConstraint('text_version > 0', name=op.f('ck_lost_report_text_features_text_version_positive')),
        sa.ForeignKeyConstraint(['profile_id'], ['text_analysis_profiles.id'], name=op.f('fk_lost_report_text_features_profile_id_text_analysis_profiles'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['report_id'], ['lost_reports.id'], name=op.f('fk_lost_report_text_features_report_id_lost_reports'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_lost_report_text_features')),
        sa.UniqueConstraint('id', 'report_id', 'profile_id', name='uq_report_id_feature_identity'),
        sa.UniqueConstraint('report_id', 'profile_id', 'text_version', name=op.f('uq_lost_report_text_features_report_id'))
    )
    op.create_index('ix_lost_report_text_features_backfill', 'lost_report_text_features', ['profile_id', 'status', 'report_id'], unique=False, postgresql_where=None)
    op.create_table('match_evaluation_jobs',
        sa.Column('item_id', sa.Uuid(), nullable=True),
        sa.Column('report_id', sa.Uuid(), nullable=True),
        sa.Column('policy_id', sa.Uuid(), nullable=False),
        sa.Column('requested_generation', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('completed_generation', sa.BigInteger(), server_default=sa.text('0'), nullable=False),
        sa.Column('claimed_generation', sa.BigInteger(), nullable=True),
        sa.Column('lease_token', sa.Uuid(), nullable=True),
        sa.Column('lease_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('attempts', sa.Integer(), server_default=sa.text('0'), nullable=False),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_error_code', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.CheckConstraint("last_error_code IS NULL OR last_error_code ~ '^[A-Z][A-Z0-9_]{0,79}$'", name=op.f('ck_match_evaluation_jobs_error_code')),
        sa.CheckConstraint('(claimed_generation IS NULL AND lease_token IS NULL AND lease_until IS NULL) OR (claimed_generation IS NOT NULL AND lease_token IS NOT NULL AND lease_until IS NOT NULL AND claimed_generation >= 1 AND claimed_generation <= requested_generation)', name=op.f('ck_match_evaluation_jobs_lease')),
        sa.CheckConstraint('(failed_at IS NULL) = (last_error_code IS NULL)', name=op.f('ck_match_evaluation_jobs_failure')),
        sa.CheckConstraint('(item_id IS NULL) <> (report_id IS NULL)', name=op.f('ck_match_evaluation_jobs_one_owner')),
        sa.CheckConstraint('attempts >= 0', name=op.f('ck_match_evaluation_jobs_attempts')),
        sa.CheckConstraint('failed_at IS NULL OR lease_token IS NULL', name=op.f('ck_match_evaluation_jobs_failed_lease')),
        sa.CheckConstraint('requested_generation > 0 AND completed_generation >= 0 AND completed_generation <= requested_generation', name=op.f('ck_match_evaluation_jobs_generations')),
        sa.ForeignKeyConstraint(['item_id'], ['found_items.id'], name=op.f('fk_match_evaluation_jobs_item_id_found_items'), ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['policy_id'], ['matching_policies.id'], name=op.f('fk_match_evaluation_jobs_policy_id_matching_policies'), ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['report_id'], ['lost_reports.id'], name=op.f('fk_match_evaluation_jobs_report_id_lost_reports'), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_match_evaluation_jobs')),
        sa.UniqueConstraint('item_id', 'policy_id', name=op.f('uq_match_evaluation_jobs_item_id')),
        sa.UniqueConstraint('report_id', 'policy_id', name=op.f('uq_match_evaluation_jobs_report_id'))
    )
    op.create_index('ix_match_evaluation_jobs_pending', 'match_evaluation_jobs', ['next_attempt_at', 'id'], unique=False, postgresql_where=sa.text('completed_generation < requested_generation AND failed_at IS NULL'))
    op.create_table('matching_runtime',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('active_policy_id', sa.Uuid(), nullable=False),
        sa.Column('generation', sa.BigInteger(), server_default=sa.text('1'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('generation > 0', name=op.f('ck_matching_runtime_generation_positive')),
        sa.CheckConstraint('id = 1', name=op.f('ck_matching_runtime_singleton')),
        sa.ForeignKeyConstraint(['active_policy_id'], ['matching_policies.id'], name=op.f('fk_matching_runtime_active_policy_id_matching_policies'), ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_matching_runtime'))
    )
    op.create_index('ix_found_items_match_date', 'found_items', ['category_id', 'found_at', 'id'], unique=False, postgresql_where=sa.text('deleted_at IS NULL'))
    op.add_column('match_candidates', sa.Column('policy_id', sa.Uuid(), nullable=True))
    op.add_column('match_candidates', sa.Column('analysis_profile_id', sa.Uuid(), nullable=True))
    op.add_column('match_candidates', sa.Column('evaluated_item_version', sa.BigInteger(), nullable=True))
    op.add_column('match_candidates', sa.Column('evaluated_report_version', sa.BigInteger(), nullable=True))
    op.add_column('match_candidates', sa.Column('item_feature_id', sa.Uuid(), nullable=True))
    op.add_column('match_candidates', sa.Column('report_feature_id', sa.Uuid(), nullable=True))
    op.add_column('match_candidates', sa.Column('common_keywords', postgresql.ARRAY(sa.Text()), server_default=sa.text("'{}'::text[]"), nullable=False))
    op.create_foreign_key('fk_match_candidate_policy_profile', 'match_candidates', 'matching_policies', ['policy_id', 'analysis_profile_id'], ['id', 'analysis_profile_id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_match_candidate_report_feature', 'match_candidates', 'lost_report_text_features', ['report_feature_id', 'report_id', 'analysis_profile_id'], ['id', 'report_id', 'profile_id'], initially='DEFERRED', deferrable=True)
    op.create_foreign_key('fk_match_candidate_item_feature', 'match_candidates', 'found_item_text_features', ['item_feature_id', 'item_id', 'analysis_profile_id'], ['id', 'item_id', 'profile_id'], initially='DEFERRED', deferrable=True)
    op.add_column('outbox_events', sa.Column('failed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('outbox_events', sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True))
    # Existing leases have no fencing token. Release them for safe reacquisition.
    op.execute('UPDATE outbox_events SET lease_until = NULL, lease_token = NULL '
               'WHERE lease_until IS NOT NULL OR lease_token IS NOT NULL')
    for table, constraints in EXISTING_CHECKS.items():
        for name, condition in constraints.items():
            op.create_check_constraint(op.f(f'ck_{table}_{name}'), table, condition)
    op.drop_index('ix_outbox_events_pending', table_name='outbox_events')
    op.create_index('ix_outbox_events_pending', 'outbox_events', ['next_attempt_at', 'id'],
                    postgresql_where=sa.text(
                        'processed_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL'))
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade():
    for table, trigger in (
        ('found_items', 'matching_text_version'),
        ('lost_reports', 'matching_text_version'),
        ('found_items', 'matching_item_redaction'),
        ('text_analysis_profiles', 'matching_immutable'),
        ('matching_policies', 'matching_immutable'),
        ('matching_runtime', 'matching_runtime_generation'),
        ('found_item_text_features', 'matching_feature_guard'),
        ('lost_report_text_features', 'matching_feature_guard'),
        ('found_item_text_features', 'matching_feature_cancel'),
        ('lost_report_text_features', 'matching_feature_cancel'),
    ):
        op.execute(f'DROP TRIGGER {trigger} ON {table}')
    for function in (
        'kaifind_matching_text_version', 'kaifind_matching_immutable',
        'kaifind_matching_runtime_generation', 'kaifind_matching_feature_guard',
        'kaifind_matching_feature_cancel', 'kaifind_matching_item_redaction',
    ):
        op.execute(f'DROP FUNCTION {function}()')
    for table, constraints in EXISTING_CHECKS.items():
        for name in constraints:
            op.drop_constraint(op.f(f'ck_{table}_{name}'), table, type_='check')
    op.drop_index('ix_outbox_events_pending', table_name='outbox_events')
    op.create_index('ix_outbox_events_pending', 'outbox_events', ['next_attempt_at', 'id'],
                    postgresql_where=sa.text('processed_at IS NULL'))
    op.drop_column('outbox_events', 'cancelled_at')
    op.drop_column('outbox_events', 'failed_at')
    op.drop_constraint('fk_match_candidate_item_feature', 'match_candidates', type_='foreignkey')
    op.drop_constraint('fk_match_candidate_report_feature', 'match_candidates', type_='foreignkey')
    op.drop_constraint('fk_match_candidate_policy_profile', 'match_candidates', type_='foreignkey')
    op.drop_column('match_candidates', 'common_keywords')
    op.drop_column('match_candidates', 'report_feature_id')
    op.drop_column('match_candidates', 'item_feature_id')
    op.drop_column('match_candidates', 'evaluated_report_version')
    op.drop_column('match_candidates', 'evaluated_item_version')
    op.drop_column('match_candidates', 'analysis_profile_id')
    op.drop_column('match_candidates', 'policy_id')
    op.drop_index('ix_found_items_match_date', table_name='found_items', postgresql_where=sa.text('deleted_at IS NULL'))
    op.drop_table('matching_runtime')
    op.drop_index('ix_match_evaluation_jobs_pending', table_name='match_evaluation_jobs', postgresql_where=sa.text('completed_generation < requested_generation AND failed_at IS NULL'))
    op.drop_table('match_evaluation_jobs')
    op.drop_index('ix_lost_report_text_features_backfill', table_name='lost_report_text_features', postgresql_where=None)
    op.drop_table('lost_report_text_features')
    op.drop_index('ix_found_item_text_features_backfill', table_name='found_item_text_features', postgresql_where=None)
    op.drop_table('found_item_text_features')
    op.drop_table('matching_policies')
    op.drop_table('text_analysis_profiles')
    restore_legacy_schema()


def restore_legacy_schema():
    """Restore the previous revision without reinterpreting new keyword hits."""
    for table in ('found_items', 'lost_reports'):
        op.alter_column(table, 'text_version', new_column_name='description_version')
        op.create_check_constraint(op.f(f'ck_{table}_description_version_positive'),
                                   table, 'description_version > 0')
    op.execute('''CREATE FUNCTION advance_description_version() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF NEW.description IS DISTINCT FROM OLD.description THEN
                NEW.description_version := OLD.description_version + 1;
            ELSE
                NEW.description_version := OLD.description_version;
            END IF;
            RETURN NEW;
        END $$''')
    for table in ('found_items', 'lost_reports'):
        op.execute(f'''CREATE TRIGGER trg_{table}_description_version
            BEFORE UPDATE ON {table} FOR EACH ROW EXECUTE FUNCTION advance_description_version()''')
    op.add_column('match_candidates', sa.Column(
        'semantic_matched', sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column('match_candidates', sa.Column('semantic_score', sa.Double(), nullable=True))
    op.add_column('match_candidates', sa.Column('matching_policy_version', sa.Text(), nullable=True))
    for column in ('item_description_version', 'report_description_version', 'item_version', 'report_version'):
        op.add_column('match_candidates', sa.Column(column, sa.BigInteger(), nullable=True))
    op.execute('''UPDATE match_candidates SET
        semantic_matched = coalesce((legacy_evidence->>'semantic_matched')::boolean, false),
        semantic_score = (legacy_evidence->>'semantic_score')::double precision,
        matching_policy_version = legacy_evidence->>'matching_policy_version',
        item_description_version = (legacy_evidence->>'item_description_version')::bigint,
        report_description_version = (legacy_evidence->>'report_description_version')::bigint,
        item_version = (legacy_evidence->>'item_version')::bigint,
        report_version = (legacy_evidence->>'report_version')::bigint
    ''')
    op.drop_constraint(op.f('ck_match_candidates_reason'), 'match_candidates', type_='check')
    op.execute('UPDATE match_candidates SET active = false '
               'WHERE active AND NOT building_matched AND NOT semantic_matched')
    for name, condition in {
        'reason': 'NOT active OR building_matched OR semantic_matched',
        'semantic_score_range': 'semantic_score IS NULL OR semantic_score BETWEEN -1 AND 1',
        'semantic_evidence': 'NOT semantic_matched OR (semantic_score IS NOT NULL '
                             'AND item_description_version IS NOT NULL AND report_description_version IS NOT NULL)',
        'evaluated_versions_positive': '(item_description_version IS NULL OR item_description_version > 0) '
                                       'AND (report_description_version IS NULL OR report_description_version > 0) '
                                       'AND (item_version IS NULL OR item_version > 0) '
                                       'AND (report_version IS NULL OR report_version > 0)',
    }.items():
        op.create_check_constraint(op.f(f'ck_match_candidates_{name}'), 'match_candidates', condition)
    op.drop_column('match_candidates', 'legacy_evidence')


# Frozen constraints: migrations never import live application metadata.
EXISTING_CHECKS = {
    'found_items': {'text_version_positive': 'text_version > 0'},
    'lost_reports': {'text_version_positive': 'text_version > 0'},
    'outbox_events': {
        'lease_pair': '(lease_until IS NULL) = (lease_token IS NULL)',
        'one_terminal': 'num_nonnulls(processed_at, failed_at, cancelled_at) <= 1',
        'terminal_lease': 'num_nonnulls(processed_at, failed_at, cancelled_at) = 0 OR lease_token IS NULL',
    },
    'match_candidates': {
        'legacy_evidence_object': "legacy_evidence IS NULL OR jsonb_typeof(legacy_evidence) = 'object'",
        'analysis_evidence':
            '(policy_id IS NULL AND analysis_profile_id IS NULL AND evaluated_item_version IS NULL '
            'AND evaluated_report_version IS NULL AND item_feature_id IS NULL AND report_feature_id IS NULL '
            'AND cardinality(common_keywords) = 0) OR '
            '(policy_id IS NOT NULL AND analysis_profile_id IS NOT NULL '
            'AND evaluated_item_version IS NOT NULL AND evaluated_item_version > 0 '
            'AND evaluated_report_version IS NOT NULL AND evaluated_report_version > 0 '
            'AND ((keyword_matched AND item_feature_id IS NOT NULL AND report_feature_id IS NOT NULL '
            'AND cardinality(common_keywords) > 0) OR '
            '(NOT keyword_matched AND cardinality(common_keywords) = 0)))',
        'common_keywords_shape': 'coalesce(array_ndims(common_keywords), 1) = 1 '
                                 'AND array_position(common_keywords, NULL) IS NULL',
    },
}

TRIGGERS = [
    """CREATE FUNCTION kaifind_matching_text_version() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE input_changed boolean;
    BEGIN
        IF TG_OP = 'INSERT' THEN
            NEW.text_version := 1;
        ELSE
            input_changed := NEW.description IS DISTINCT FROM OLD.description;
            IF TG_TABLE_NAME = 'found_items' THEN
                input_changed := input_changed OR (to_jsonb(NEW)->'title' IS DISTINCT FROM to_jsonb(OLD)->'title');
            END IF;
            NEW.text_version := OLD.text_version + CASE WHEN input_changed THEN 1 ELSE 0 END;
        END IF;
        RETURN NEW;
    END $$""",
    """CREATE TRIGGER matching_text_version BEFORE INSERT OR UPDATE ON found_items
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_text_version()""",
    """CREATE TRIGGER matching_text_version BEFORE INSERT OR UPDATE ON lost_reports
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_text_version()""",
    """CREATE FUNCTION kaifind_matching_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        RAISE EXCEPTION 'Matching profiles and policies are immutable' USING ERRCODE = '23514';
    END $$""",
    """CREATE TRIGGER matching_immutable BEFORE UPDATE ON text_analysis_profiles
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_immutable()""",
    """CREATE TRIGGER matching_immutable BEFORE UPDATE ON matching_policies
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_immutable()""",
    """CREATE FUNCTION kaifind_matching_runtime_generation() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.active_policy_id IS DISTINCT FROM OLD.active_policy_id THEN
            NEW.generation := OLD.generation + 1;
        ELSE
            NEW.generation := OLD.generation;
        END IF;
        NEW.updated_at := now();
        RETURN NEW;
    END $$""",
    """CREATE TRIGGER matching_runtime_generation BEFORE UPDATE ON matching_runtime
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_runtime_generation()""",
    """CREATE FUNCTION kaifind_matching_feature_guard() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE canonical text[];
    BEGIN
        IF TG_OP = 'UPDATE' THEN
            IF (to_jsonb(NEW) - ARRAY['status','translated_text','keywords','attributes','updated_at','completed_at','last_error_code'])
                IS DISTINCT FROM
                (to_jsonb(OLD) - ARRAY['status','translated_text','keywords','attributes','updated_at','completed_at','last_error_code']) THEN
                RAISE EXCEPTION 'Analysis input identity is immutable' USING ERRCODE = '23514';
            END IF;
            IF OLD.status = 'READY' AND NEW IS DISTINCT FROM OLD THEN
                RAISE EXCEPTION 'Ready analysis is immutable' USING ERRCODE = '23514';
            END IF;
        END IF;
        IF NEW.keywords IS NOT NULL THEN
            SELECT coalesce(array_agg(token ORDER BY token COLLATE "C"), ARRAY[]::text[])
            INTO canonical FROM (SELECT DISTINCT unnest(NEW.keywords) AS token) tokens;
            IF NEW.keywords IS DISTINCT FROM canonical OR EXISTS (
                SELECT 1 FROM unnest(NEW.keywords) AS token WHERE token IS NULL OR btrim(token) = ''
            ) THEN
                RAISE EXCEPTION 'Keywords must be sorted, unique, nonblank tokens' USING ERRCODE = '23514';
            END IF;
        END IF;
        RETURN NEW;
    END $$""",
    """CREATE TRIGGER matching_feature_guard BEFORE INSERT OR UPDATE ON found_item_text_features
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_feature_guard()""",
    """CREATE TRIGGER matching_feature_guard BEFORE INSERT OR UPDATE ON lost_report_text_features
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_feature_guard()""",
    """CREATE FUNCTION kaifind_matching_feature_cancel() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE analysis_event text;
    BEGIN
        analysis_event := CASE WHEN TG_TABLE_NAME = 'found_item_text_features'
            THEN 'FOUND_ITEM_TEXT_ANALYSIS_REQUESTED' ELSE 'LOST_REPORT_TEXT_ANALYSIS_REQUESTED' END;
        UPDATE outbox_events SET cancelled_at = now(), lease_token = NULL, lease_until = NULL
        WHERE aggregate_id = OLD.id AND event_type = analysis_event
            AND processed_at IS NULL AND failed_at IS NULL AND cancelled_at IS NULL;
        RETURN OLD;
    END $$""",
    """CREATE TRIGGER matching_feature_cancel BEFORE DELETE ON found_item_text_features
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_feature_cancel()""",
    """CREATE TRIGGER matching_feature_cancel BEFORE DELETE ON lost_report_text_features
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_feature_cancel()""",
    """CREATE FUNCTION kaifind_matching_item_redaction() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.deleted_at IS NOT NULL AND OLD.deleted_at IS NULL THEN
            DELETE FROM match_candidates WHERE item_id = NEW.id;
            DELETE FROM found_item_text_features WHERE item_id = NEW.id;
            DELETE FROM match_evaluation_jobs WHERE item_id = NEW.id;
        END IF;
        RETURN NEW;
    END $$""",
    """CREATE TRIGGER matching_item_redaction BEFORE UPDATE ON found_items
    FOR EACH ROW EXECUTE FUNCTION kaifind_matching_item_redaction()""",
]
