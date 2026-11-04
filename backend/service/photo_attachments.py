"""Attach inside the found-item writer's transaction; lock before cleanup can run."""

from sqlalchemy import select

from model import Category, FoundItem, Photo, PhotoAttachment
from service.auth import AuthError


async def attach_photo(
    db,
    *,
    photo_id,
    item,
    user,
    now,
    alt_text,
    purpose='ITEM',
    display_order=0,
    drop_off_version=None,
):
    if not isinstance(alt_text, str) or not 1 <= len(alt_text.strip()) <= 200:
        raise AuthError(400, 'VALIDATION_ERROR')

    item = await db.scalar(select(FoundItem).where(FoundItem.id == item.id).with_for_update())
    if item is None or item.deleted_at is not None or item.finder_id != user.id:
        raise AuthError(400, 'INVALID_REFERENCE')

    photo = await db.scalar(select(Photo).where(Photo.id == photo_id).with_for_update())
    if photo is None:
        raise AuthError(400, 'INVALID_REFERENCE')
    if photo.uploader_id != user.id:
        raise AuthError(403, 'PHOTO_FORBIDDEN')

    existing = await db.get(PhotoAttachment, photo_id)
    if existing is not None:
        raise AuthError(409, 'PHOTO_ALREADY_ATTACHED')

    if photo.purpose != purpose or (photo.unattached_expires_at is None or now >= photo.unattached_expires_at):
        raise AuthError(400, 'INVALID_REFERENCE')
    if (purpose == 'DROP_OFF') != (drop_off_version is not None):
        raise AuthError(400, 'INVALID_REFERENCE')
    if drop_off_version is not None and drop_off_version.item_id != item.id:
        raise AuthError(400, 'INVALID_REFERENCE')

    # Take the category's share lock so a concurrent sensitivity change cannot
    # race the permanent protection label established on this attachment.
    category = await db.scalar(select(Category).where(Category.id == item.category_id).with_for_update(read=True))
    attachment = PhotoAttachment(
        photo_id=photo.id,
        item_id=item.id,
        drop_off_version_id=drop_off_version.id if drop_off_version else None,
        display_order=None if drop_off_version else display_order,
        alt_text=alt_text.strip(),
        attached_at=now,
        sensitive_latched=bool(
            category.sensitive
            or (drop_off_version and drop_off_version.sensitive_latched)
        ),
    )

    photo.unattached_expires_at = None
    db.add(attachment)
    await db.flush()

    return attachment
