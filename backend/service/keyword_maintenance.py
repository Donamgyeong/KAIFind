"""Bounded retention and explicit recovery of failed keyword registrations."""

from datetime import timedelta

from sqlalchemy import select, update

from model import KeywordRegistrationEvent, KeywordSubscriptionFeature
from service.outbox_worker import utcnow


async def retry_event(db, event_id, *, now=None):
    now = now or utcnow()
    event = await db.scalar(select(KeywordRegistrationEvent).where(
        KeywordRegistrationEvent.id == event_id,
        KeywordRegistrationEvent.status == 'FAILED',
    ).with_for_update())
    if event is None or (event.terms is None and event.source_description is None):
        raise ValueError('Only recoverable failed keyword events may be retried')
    # A profile reanalysis that had no terms can be repaired explicitly after
    # correcting the runtime/profile. Other subscriptions are left untouched.
    await db.execute(KeywordSubscriptionFeature.__table__.delete().where(
        KeywordSubscriptionFeature.profile_id == event.profile_id,
        KeywordSubscriptionFeature.status == 'FAILED',
    ))
    event.status = 'READY' if event.terms is not None else 'PENDING'
    event.failed_at = event.last_error_code = event.lease_token = event.lease_until = None
    event.attempts, event.next_attempt_at = 0, now


async def cleanup(db, *, now=None):
    now = now or utcnow()
    # Unprocessed snapshots also expire if workers have been disabled for a month.
    expired = await db.execute(update(KeywordRegistrationEvent).where(
        KeywordRegistrationEvent.source_description.is_not(None),
        KeywordRegistrationEvent.registered_at <= now - timedelta(days=30),
        (KeywordRegistrationEvent.lease_until.is_(None)) | (KeywordRegistrationEvent.lease_until <= now),
    ).values(
        status='CANCELLED', source_title=None, source_description=None,
        lease_token=None, lease_until=None, completed_at=now,
        last_error_code='KEYWORD_SNAPSHOT_EXPIRED',
    ))
    await db.execute(update(KeywordRegistrationEvent).where(
        KeywordRegistrationEvent.status.in_(('DONE', 'CANCELLED')),
        KeywordRegistrationEvent.completed_at <= now - timedelta(days=7),
    ).values(terms=None, cursor_user_id=None))
    return expired.rowcount
