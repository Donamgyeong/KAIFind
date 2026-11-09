"""Atomic notification insertion; the caller owns domain locks and commit."""

from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from model import EmailDeliveryItem, Notification, NotificationKeywordSource, NotificationSetting


EMAIL_FLAGS = {
    'MATCH_CANDIDATE': 'match_email', 'ITEM_COLLECTED': 'collection_email',
    'ITEM_EXPIRED': 'expiry_email', 'KEYWORD_MATCH': 'keyword_email',
}


async def email_allowed(db, recipient_id, kind):
    settings = await db.get(NotificationSetting, recipient_id)
    return settings is None or (settings.email_enabled and getattr(settings, EMAIL_FLAGS[kind]))


async def create_notification(
    db, *, event_id, recipient_id, kind, item_id, now, report_id=None, subscription_ids=(),
):
    notification_id = await db.scalar(insert(Notification).values(
        event_id=event_id, recipient_id=recipient_id, type=kind,
        item_id=item_id, report_id=report_id, created_at=now,
        purge_after=now + timedelta(days=365),
    ).on_conflict_do_nothing(
        index_elements=['event_id', 'recipient_id', 'type'],
    ).returning(Notification.id))
    if notification_id is None:
        return await db.scalar(select(Notification.id).where(
            Notification.event_id == event_id, Notification.recipient_id == recipient_id,
            Notification.type == kind,
        ))

    for subscription_id in set(subscription_ids):
        await db.execute(insert(NotificationKeywordSource).values(
            notification_id=notification_id, subscription_id=subscription_id,
        ).on_conflict_do_nothing())
    if await email_allowed(db, recipient_id, kind):
        await db.execute(insert(EmailDeliveryItem).values(
            notification_id=notification_id, created_at=now,
        ).on_conflict_do_nothing(index_elements=['notification_id']))
    return notification_id
