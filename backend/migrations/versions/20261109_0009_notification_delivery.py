"""Configurable email policies, fenced deliveries and transactional domain events."""

from alembic import op
import re
import sqlalchemy as sa


revision = '20261109_0009'
down_revision = '20261108_0008'
branch_labels = None
depends_on = None


TRIGGERS = '''
CREATE FUNCTION enqueue_collection_notification() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    INSERT INTO outbox_events
        (id,event_type,aggregate_id,aggregate_version,payload)
    VALUES (gen_random_uuid(),'COLLECTION_NOTIFICATION',NEW.id,1,
            jsonb_build_object('collectionId',NEW.id,'itemId',NEW.item_id))
    ON CONFLICT (aggregate_id,aggregate_version,event_type) DO NOTHING;
    RETURN NEW;
END $$;
CREATE TRIGGER collection_notification AFTER INSERT ON collections
    FOR EACH ROW EXECUTE FUNCTION enqueue_collection_notification();

CREATE FUNCTION enqueue_expiry_notification() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.status <> 'EXPIRED' AND NEW.status = 'EXPIRED' THEN
        INSERT INTO outbox_events
            (id,event_type,aggregate_id,aggregate_version,payload)
        VALUES (gen_random_uuid(),'EXPIRY_NOTIFICATION',NEW.id,NEW.version,
                jsonb_build_object('itemId',NEW.id))
        ON CONFLICT (aggregate_id,aggregate_version,event_type) DO NOTHING;
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER expiry_notification AFTER UPDATE OF status ON found_items
    FOR EACH ROW EXECUTE FUNCTION enqueue_expiry_notification();
'''


def upgrade():
    op.create_table(
        'email_delivery_policies',
        sa.Column('delivery_date', sa.Date(), primary_key=True),
        sa.Column('daily_limit', sa.Integer(), nullable=False),
        sa.Column('digest_time', sa.Time(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.CheckConstraint('daily_limit >= 1', name=op.f('ck_email_delivery_policies_daily_limit')),
    )
    op.execute('''INSERT INTO email_delivery_policies (delivery_date,daily_limit,digest_time)
                  SELECT DISTINCT delivery_date,20,time '20:00' FROM email_deliveries''')
    op.create_foreign_key(op.f('fk_email_deliveries_delivery_date_email_delivery_policies'),
                          'email_deliveries', 'email_delivery_policies', ['delivery_date'], ['delivery_date'])
    op.add_column('email_deliveries', sa.Column('lease_token', sa.Uuid(), nullable=True))
    op.drop_constraint(op.f('ck_email_deliveries_slot'), 'email_deliveries', type_='check')
    op.create_check_constraint(op.f('ck_email_deliveries_slot'), 'email_deliveries',
                               "kind IN ('INDIVIDUAL','DIGEST') AND slot_no >= 1")
    op.drop_constraint(op.f('ck_email_deliveries_status'), 'email_deliveries', type_='check')
    op.create_check_constraint(op.f('ck_email_deliveries_status'), 'email_deliveries',
                               "status IN ('PENDING','SENDING','SENT','RETRY','FAILED','CANCELLED','UNKNOWN')")
    op.create_index('uq_email_deliveries_digest', 'email_deliveries', ['recipient_id','delivery_date'],
                    unique=True, postgresql_where=sa.text("kind = 'DIGEST'"))
    op.create_index('ix_email_delivery_items_pending', 'email_delivery_items', ['created_at','id'],
                    postgresql_where=sa.text("status = 'PENDING'"))
    op.create_table(
        'mock_email_receipts',
        sa.Column('delivery_id', sa.Uuid(), primary_key=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=False),
    )
    # psycopg can execute multi-statement SQL; asyncpg requires separate statements.
    for statement in re.split(r'(?<=;)\s*(?=CREATE)', TRIGGERS.strip()):
        op.execute(statement)


def downgrade():
    incompatible = op.get_bind().scalar(sa.text('''SELECT
        EXISTS (SELECT 1 FROM email_deliveries WHERE status='UNKNOWN' OR
            NOT ((kind='INDIVIDUAL' AND slot_no BETWEEN 1 AND 19) OR (kind='DIGEST' AND slot_no=20)))
        OR EXISTS (SELECT 1 FROM mock_email_receipts)
        OR EXISTS (SELECT 1 FROM outbox_events WHERE event_type IN
            ('COLLECTION_NOTIFICATION','EXPIRY_NOTIFICATION'))'''))
    if incompatible:
        raise RuntimeError('Notification delivery history prevents downgrade; retain this revision')
    op.execute('DROP TRIGGER expiry_notification ON found_items')
    op.execute('DROP FUNCTION enqueue_expiry_notification()')
    op.execute('DROP TRIGGER collection_notification ON collections')
    op.execute('DROP FUNCTION enqueue_collection_notification()')
    op.drop_table('mock_email_receipts')
    op.drop_index('ix_email_delivery_items_pending', table_name='email_delivery_items')
    op.drop_index('uq_email_deliveries_digest', table_name='email_deliveries')
    op.drop_constraint(op.f('ck_email_deliveries_status'), 'email_deliveries', type_='check')
    op.create_check_constraint(op.f('ck_email_deliveries_status'), 'email_deliveries',
                               "status IN ('PENDING','SENDING','SENT','RETRY','FAILED','CANCELLED')")
    op.drop_constraint(op.f('ck_email_deliveries_slot'), 'email_deliveries', type_='check')
    op.create_check_constraint(op.f('ck_email_deliveries_slot'), 'email_deliveries',
                               "(kind='INDIVIDUAL' AND slot_no BETWEEN 1 AND 19) OR (kind='DIGEST' AND slot_no=20)")
    op.drop_column('email_deliveries', 'lease_token')
    op.drop_constraint(op.f('fk_email_deliveries_delivery_date_email_delivery_policies'),
                        'email_deliveries', type_='foreignkey')
    op.drop_table('email_delivery_policies')
