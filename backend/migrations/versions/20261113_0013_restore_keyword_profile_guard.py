"""Restore the keyword profile guard in databases with schema drift."""

from alembic import op


revision = '20261113_0013'
down_revision = '20261109_0012'
branch_labels = None
depends_on = None


FUNCTION = '''CREATE OR REPLACE FUNCTION keyword_profile_drain() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE profile uuid;
BEGIN
    IF NEW.active_policy_id IS DISTINCT FROM OLD.active_policy_id THEN
        PERFORM pg_advisory_xact_lock(73011810);
        SELECT analysis_profile_id INTO profile
        FROM matching_policies WHERE id = NEW.active_policy_id;
        IF EXISTS (
            SELECT 1 FROM keyword_registration_events
            WHERE status IN ('PENDING', 'READY', 'FAILED')
              AND profile_id IS NOT NULL AND profile_id <> profile
        ) THEN
            RAISE EXCEPTION 'Drain keyword registration events before profile activation';
        END IF;
    END IF;
    RETURN NEW;
END $$'''


def upgrade():
    op.execute(FUNCTION)
    op.execute('''DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger
            WHERE tgrelid = 'matching_runtime'::regclass
              AND tgname = 'keyword_profile_drain' AND NOT tgisinternal
        ) THEN
            CREATE TRIGGER keyword_profile_drain
            BEFORE UPDATE OF active_policy_id ON matching_runtime
            FOR EACH ROW EXECUTE FUNCTION keyword_profile_drain();
        END IF;
    END $$''')
    op.execute('ALTER TABLE matching_runtime ENABLE TRIGGER keyword_profile_drain')


def downgrade():
    # The function and trigger belong to revision 0010. Keep the repaired guard
    # when returning to 0012; revision 0010 still owns their eventual removal.
    pass
