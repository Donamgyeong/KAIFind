"""Found item registration uses the caller's authenticated transaction."""

from datetime import timedelta

from sqlalchemy import select

from library.matching_lock import lock_matching_categories
from model import Building, Category, DropOffVersion, FoundItem, Photo
from schema.found_items import DropOffLocation, FoundItemDetail
from service.audit import append_audit
from service.auth import AuthError
from service.photo_attachments import attach_photo
from service.text_analysis import analysis_status, request_found_item_analysis


class FoundItemService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user
        self.now = request.state.now

    async def create(self, body):
        if body.found_at > self.now:
            raise AuthError(400, 'VALIDATION_ERROR', fields=[
                {'field': 'foundAt', 'code': 'INVALID_FORMAT'},
            ])

        await lock_matching_categories(self.db, [body.category_id])
        category = await self.db.scalar(select(Category).where(
            Category.id == body.category_id,
        ).with_for_update(read=True))
        location = body.drop_off
        building_ids = {body.found_building_id}
        if isinstance(location, DropOffLocation):
            building_ids.add(location.building_id)
        buildings = {row.id: row for row in (await self.db.scalars(select(Building).where(
            Building.id.in_(building_ids),
        ).order_by(Building.id).with_for_update(read=True))).all()}
        if (category is None or not category.active or len(buildings) != len(building_ids)
                or any(not building.active for building in buildings.values())):
            raise AuthError(400, 'INVALID_REFERENCE')

        item = FoundItem(
            finder_id=self.user.id, category_id=category.id, title=body.title,
            description=body.description, found_building_id=body.found_building_id,
            found_location_description=body.found_location_description, found_at=body.found_at,
            status='POSTED', hidden=False, created_at=self.now, updated_at=self.now,
            posted_at=self.now, expires_at=self.now + timedelta(days=30),
        )
        self.db.add(item)
        await self.db.flush()

        drop_off = DropOffVersion(
            item_id=item.id, revision_no=1, mode=location.mode,
            building_id=location.building_id if isinstance(location, DropOffLocation) else None,
            spot_description=location.spot_description if isinstance(location, DropOffLocation) else None,
            changed_by_user_id=self.user.id, changed_at=self.now,
            sensitive_latched=category.sensitive,
        )
        self.db.add(drop_off)
        await self.db.flush()

        storage_photo = location.photo if isinstance(location, DropOffLocation) else None
        photo_ids = [photo.photo_id for photo in body.photos]
        if storage_photo:
            photo_ids.append(storage_photo.photo_id)
        # Lock the whole set before attachment helpers, regardless of display order.
        await self.db.execute(select(Photo).where(Photo.id.in_(photo_ids)).order_by(
            Photo.id,
        ).with_for_update())
        attachments = []
        for order, photo in enumerate(body.photos):
            attachments.append(await attach_photo(
                self.db, photo_id=photo.photo_id, item=item, user=self.user,
                now=self.now, alt_text=photo.alt_text, display_order=order,
            ))
        if storage_photo:
            await attach_photo(
                self.db, photo_id=storage_photo.photo_id, item=item, user=self.user,
                now=self.now, alt_text=storage_photo.alt_text, purpose='DROP_OFF',
                drop_off_version=drop_off,
            )

        await request_found_item_analysis(self.db, item=item, now=self.now)
        append_audit(self.db, self.user, 'ITEM_STATUS_CHANGED', 'FOUND_ITEM', item.id,
                     self.now, toStatus='POSTED')
        append_audit(self.db, self.user, 'DROP_OFF_CHANGED', 'FOUND_ITEM', item.id, self.now)
        await self.db.flush()
        await self.db.refresh(item)

        return FoundItemDetail(
            itemId=item.id,
            category=dict(categoryId=category.id, nameKo=category.name_ko, nameEn=category.name_en,
                          active=category.active, sensitive=category.sensitive),
            title=item.title, status=item.status,
            foundBuilding=dict(
                buildingId=buildings[item.found_building_id].id,
                code=buildings[item.found_building_id].code,
                nameKo=buildings[item.found_building_id].name_ko,
                nameEn=buildings[item.found_building_id].name_en,
                active=buildings[item.found_building_id].active,
            ),
            foundAt=item.found_at, createdAt=item.created_at,
            photos=[dict(photoId=row.photo_id, altText=row.alt_text,
                         accessRequiresLogin=row.sensitive_latched) for row in attachments],
            sensitive=category.sensitive, hidden=item.hidden,
            description=item.description, foundLocationDescription=item.found_location_description,
            finder=dict(userId=item.finder_id), analysisStatus=await analysis_status(self.db, owner=item),
            updatedAt=item.updated_at, postedAt=item.posted_at,
            expiresAt=item.expires_at, closedAt=item.closed_at,
        )
