"""All-word subscriptions and atomic registration snapshots."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY


revision = '20261109_0010'
down_revision = '20261109_0009'
branch_labels = None
depends_on = None


TRIGGERS = [
    '''CREATE FUNCTION keyword_profile_drain() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE profile uuid;
    BEGIN
        IF NEW.active_policy_id IS DISTINCT FROM OLD.active_policy_id THEN
            PERFORM pg_advisory_xact_lock(73011810);
            SELECT analysis_profile_id INTO profile FROM matching_policies WHERE id=NEW.active_policy_id;
            IF EXISTS (SELECT 1 FROM keyword_registration_events
                       WHERE status IN ('PENDING','READY','FAILED') AND profile_id IS NOT NULL
                       AND profile_id <> profile) THEN
                RAISE EXCEPTION 'Drain keyword registration events before profile activation';
            END IF;
        END IF;
        RETURN NEW;
    END $$''',
    '''CREATE TRIGGER keyword_profile_drain BEFORE UPDATE OF active_policy_id ON matching_runtime
       FOR EACH ROW EXECUTE FUNCTION keyword_profile_drain()''',
    '''CREATE FUNCTION keyword_subscription_order() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        PERFORM pg_advisory_xact_lock(73011810);
        NEW.registration_order := nextval('keyword_registration_order');
        NEW.created_at := clock_timestamp();
        RETURN NEW;
    END $$''',
    '''CREATE TRIGGER keyword_subscription_order BEFORE INSERT ON keyword_subscriptions
       FOR EACH ROW EXECUTE FUNCTION keyword_subscription_order()''',
    '''CREATE FUNCTION keyword_item_registered() RETURNS trigger LANGUAGE plpgsql AS $$
    DECLARE profile uuid;
    BEGIN
        PERFORM pg_advisory_xact_lock(73011810);
        SELECT p.analysis_profile_id INTO profile FROM matching_runtime r
            JOIN matching_policies p ON p.id=r.active_policy_id WHERE r.id=1;
        INSERT INTO keyword_registration_events
            (id,item_id,registered_at,registration_order,profile_id,source_title,source_description)
        VALUES (gen_random_uuid(),NEW.id,clock_timestamp(),nextval('keyword_registration_order'),
                profile,NEW.title,NEW.description);
        RETURN NEW;
    END $$''',
    '''CREATE TRIGGER keyword_item_registered AFTER INSERT ON found_items
       FOR EACH ROW EXECUTE FUNCTION keyword_item_registered()''',
    '''CREATE FUNCTION keyword_item_cancelled() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
        IF NEW.hidden OR NEW.deleted_at IS NOT NULL OR NEW.status <> 'POSTED' THEN
            UPDATE keyword_registration_events SET status='CANCELLED',
                source_title=NULL,source_description=NULL,lease_token=NULL,lease_until=NULL,
                completed_at=clock_timestamp()
            WHERE item_id=NEW.id AND status NOT IN ('DONE','CANCELLED');
        END IF;
        RETURN NEW;
    END $$''',
    '''CREATE TRIGGER keyword_item_cancelled AFTER UPDATE OF hidden,deleted_at,status ON found_items
       FOR EACH ROW EXECUTE FUNCTION keyword_item_cancelled()''',
]


def upgrade():
    op.execute('CREATE SEQUENCE keyword_registration_order')
    op.add_column('keyword_subscriptions', sa.Column(
        'registration_order', sa.BigInteger(), nullable=False,
        server_default=sa.text("nextval('keyword_registration_order')"),
    ))
    op.create_table(
        'keyword_subscription_features',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('subscription_id', sa.Uuid(), sa.ForeignKey('keyword_subscriptions.id', ondelete='CASCADE'), nullable=False),
        sa.Column('profile_id', sa.Uuid(), sa.ForeignKey('text_analysis_profiles.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('rule_version', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False),
        sa.Column('terms', ARRAY(sa.Text())),
        sa.Column('source_hash', sa.Text(), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_error_code', sa.Text()),
        sa.UniqueConstraint('subscription_id', 'profile_id', 'rule_version'),
        sa.CheckConstraint("status IN ('READY','FAILED')", name='status'),
        sa.CheckConstraint("(status = 'READY' AND terms IS NOT NULL AND cardinality(terms) > 0 AND last_error_code IS NULL) OR "
                           "(status = 'FAILED' AND terms IS NULL AND last_error_code IS NOT NULL)", name='result'),
        sa.CheckConstraint('terms IS NULL OR array_position(terms, NULL) IS NULL', name='terms'),
    )
    op.create_table(
        'keyword_registration_events',
        sa.Column('id', sa.Uuid(), primary_key=True),
        sa.Column('item_id', sa.Uuid(), sa.ForeignKey('found_items.id', ondelete='CASCADE'), nullable=False),
        sa.Column('registered_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('registration_order', sa.BigInteger(), nullable=False),
        sa.Column('profile_id', sa.Uuid(), sa.ForeignKey('text_analysis_profiles.id', ondelete='RESTRICT')),
        sa.Column('rule_version', sa.Text(), nullable=False, server_default=sa.text("'all-atomic-terms-v1'")),
        sa.Column('status', sa.Text(), nullable=False, server_default=sa.text("'PENDING'")),
        sa.Column('source_title', sa.Text()), sa.Column('source_description', sa.Text()),
        sa.Column('source_hash', sa.Text()), sa.Column('terms', ARRAY(sa.Text())),
        sa.Column('cursor_user_id', sa.Uuid()),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('next_attempt_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('lease_token', sa.Uuid()), sa.Column('lease_until', sa.DateTime(timezone=True)),
        sa.Column('completed_at', sa.DateTime(timezone=True)), sa.Column('failed_at', sa.DateTime(timezone=True)),
        sa.Column('last_error_code', sa.Text()),
        sa.UniqueConstraint('item_id'),
        sa.CheckConstraint("status IN ('PENDING','READY','DONE','CANCELLED','FAILED')", name='status'),
        sa.CheckConstraint('(lease_token IS NULL) = (lease_until IS NULL)', name='lease'),
        sa.CheckConstraint('attempts >= 0', name='attempts'),
        sa.CheckConstraint('terms IS NULL OR array_position(terms, NULL) IS NULL', name='terms'),
        sa.CheckConstraint("status <> 'READY' OR (terms IS NOT NULL AND profile_id IS NOT NULL)", name='ready'),
    )
    op.create_index('ix_keyword_registration_events_pending', 'keyword_registration_events', ['next_attempt_at', 'id'],
                    postgresql_where=sa.text("status IN ('PENDING','READY')"))
    op.create_index('ix_keyword_subscriptions_owner', 'keyword_subscriptions', ['user_id', sa.text('created_at DESC'), sa.text('id DESC')])
    for statement in TRIGGERS:
        op.execute(statement)


def downgrade():
    if op.get_bind().scalar(sa.text('SELECT EXISTS (SELECT 1 FROM keyword_registration_events) '
                                  'OR EXISTS (SELECT 1 FROM keyword_subscription_features)')):
        raise RuntimeError('Keyword history prevents downgrade; retain this revision')
    for trigger, table in (
        ('keyword_profile_drain', 'matching_runtime'),
        ('keyword_item_cancelled', 'found_items'), ('keyword_item_registered', 'found_items'),
        ('keyword_subscription_order', 'keyword_subscriptions'),
    ):
        op.execute(f'DROP TRIGGER {trigger} ON {table}')
        op.execute(f'DROP FUNCTION {trigger}()')
    op.drop_index('ix_keyword_subscriptions_owner', table_name='keyword_subscriptions')
    op.drop_table('keyword_registration_events')
    op.drop_table('keyword_subscription_features')
    op.drop_column('keyword_subscriptions', 'registration_order')
    op.execute('DROP SEQUENCE keyword_registration_order')
