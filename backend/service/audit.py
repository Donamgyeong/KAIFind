"""Append audit events inside the caller's transaction; never commit independently."""
from typing import get_args
from uuid import UUID

from model import AuditLog
from schema.admin import AuditAction

TARGETS = {'FOUND_ITEM', 'LOST_REPORT', 'COLLECTION', 'USER', 'BUILDING', 'CATEGORY', 'POST_REPORT', 'DISPUTE'}
UUID_KEYS = {'collectionId', 'photoId', 'reportId', 'disputeId'}


def one_year_after(now):
    try:
        return now.replace(year=now.year + 1)
    except ValueError:  # February 29
        return now.replace(year=now.year + 1, day=28)


def append_audit(db, actor, action, target_type, target_id, now, **metadata):
    if action not in get_args(AuditAction) or target_type not in TARGETS:
        raise ValueError('unknown audit event')
    for key, value in metadata.items():
        if key in UUID_KEYS:
            metadata[key] = str(UUID(str(value)))
        elif key in {'fromRole', 'toRole'}:
            if value not in {'MEMBER', 'ADMIN'}:
                raise ValueError('invalid audit role')
        elif key in {'fromStatus', 'toStatus'}:
            allowed = {'OPEN', 'RESOLVED', 'CLOSED'} if target_type == 'LOST_REPORT' else {'POSTED', 'COLLECTED', 'EXPIRED'}
            if value not in allowed:
                raise ValueError('invalid audit status')
        elif key == 'restricted':
            if type(value) is not bool:
                raise ValueError('invalid audit restriction')
        elif key == 'decision':
            if value not in {'HIDE', 'DISMISS', 'UPHELD', 'DISMISSED'}:
                raise ValueError('invalid audit decision')
        else:
            raise ValueError('unknown audit metadata')
    db.add(AuditLog(actor_id=actor.id if actor else None,
        actor_type=actor.role if actor else 'SYSTEM', action=action,
        target_type=target_type, target_id=target_id, event_metadata=metadata,
        occurred_at=now, purge_after=one_year_after(now)))
