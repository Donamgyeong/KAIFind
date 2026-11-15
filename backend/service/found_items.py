"""Found item operations run inside the caller's transaction (protected or optional-auth)."""

from collections import defaultdict
from datetime import datetime, time, timedelta

from sqlalchemy import func, inspect, or_, select
from sqlalchemy.orm.attributes import flag_modified

from library.matching_lock import lock_matching_categories
from model import (
    Building, Category, DropOffVersion, FoundItem, MatchingRuntime, Photo, PhotoAttachment,
)
from schema.found_items import (
    DropOffHistoryEntry, DropOffHistoryPage, DropOffLocation, DropOffResponse, FoundItemDetail,
    FoundItemPage, FoundItemSummary,
)
from service.audit import append_audit, one_year_after
from service.auth import AuthError
from service.matching import KST
from service.photo_attachments import attach_photo
from service.text_analysis import (
    analysis_status, request_found_item_analysis, request_item_reevaluation,
)


class FoundItemService:
    def __init__(self, request):
        self.db = request.state.db
        # None for a guest on an optional-auth route; protected routes always set a member.
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

    # ------------------------------------------------------------------ access

    def is_finder(self, item):
        return self.user is not None and self.user.id == item.finder_id

    def can_see_hidden(self, item):
        return self.is_finder(item) or (self.user is not None and self.user.role == 'ADMIN')

    def require_finder(self, item):
        # ADMIN is not an implicit editor of other members' posts.
        if not self.is_finder(item):
            raise AuthError(403, 'FORBIDDEN')

    async def load(self, item_id, *, writing=False, extra_categories=()):
        """Fetch a live item the caller may see; writers lock category, then the row."""
        category = await self.db.scalar(select(FoundItem.category_id).where(FoundItem.id == item_id))
        if category is None:
            raise AuthError(404, 'NOT_FOUND')
        if writing:
            await lock_matching_categories(self.db, [category, *extra_categories])

        query = select(FoundItem).where(FoundItem.id == item_id).execution_options(populate_existing=True)
        item = await self.db.scalar(query.with_for_update() if writing else query)
        if item is None or item.deleted_at is not None:
            raise AuthError(404, 'NOT_FOUND')
        if writing and item.category_id != category:
            raise AuthError(409, 'CONCURRENT_MODIFICATION')

        # Hidden posts exist only for their finder and administrators.
        if item.hidden and not self.can_see_hidden(item):
            raise AuthError(404, 'NOT_FOUND')
        return item

    # ------------------------------------------------------- response assembly

    async def related(self, items):
        """Batch-load categories, buildings and item photos for several items at once."""
        categories = {row.id: row for row in (await self.db.scalars(select(Category).where(
            Category.id.in_({item.category_id for item in items}),
        ))).all()}
        buildings = {row.id: row for row in (await self.db.scalars(select(Building).where(
            Building.id.in_({item.found_building_id for item in items}),
        ))).all()}

        # Storage-spot photos (drop_off_version_id set) never belong to an item response.
        photos = defaultdict(list)
        attachments = (await self.db.scalars(select(PhotoAttachment).where(
            PhotoAttachment.item_id.in_([item.id for item in items]),
            PhotoAttachment.drop_off_version_id.is_(None),
            PhotoAttachment.detached_at.is_(None),
        ).order_by(PhotoAttachment.item_id, PhotoAttachment.display_order).execution_options(
            # A DB trigger may have raised protection labels earlier in this transaction.
            populate_existing=True,
        ))).all()
        for row in attachments:
            photos[row.item_id].append(row)
        return categories, buildings, photos

    def summary_data(self, item, category, building, attachments):
        # Guests never see metadata or alt text of protected (sensitive) photos.
        guest = self.user is None
        visible = [row for row in attachments
                   if not (guest and (row.sensitive_latched or category.sensitive))]
        return dict(
            itemId=item.id,
            category=dict(categoryId=category.id, nameKo=category.name_ko,
                          nameEn=category.name_en, active=category.active,
                          sensitive=category.sensitive),
            title=item.title, status=item.status,
            foundBuilding=dict(buildingId=building.id, code=building.code,
                               nameKo=building.name_ko, nameEn=building.name_en,
                               active=building.active),
            foundAt=item.found_at, createdAt=item.created_at,
            photos=[dict(photoId=row.photo_id, altText=row.alt_text,
                         accessRequiresLogin=row.sensitive_latched) for row in visible],
            sensitive=category.sensitive, hidden=item.hidden,
        )

    async def summaries(self, items):
        if not items:
            return []
        categories, buildings, photos = await self.related(items)
        return [
            FoundItemSummary(**self.summary_data(
                item, categories[item.category_id], buildings[item.found_building_id], photos[item.id],
            ))
            for item in items
        ]

    async def detail(self, item):
        # Server-side defaults (updated_at, text_version) are expired after a flush.
        if inspect(item).expired_attributes:
            await self.db.refresh(item)
        categories, buildings, photos = await self.related([item])
        data = self.summary_data(
            item, categories[item.category_id], buildings[item.found_building_id], photos[item.id],
        )
        return FoundItemDetail(
            **data, description=item.description,
            analysisStatus=await analysis_status(self.db, owner=item),
            foundLocationDescription=item.found_location_description,
            finder=dict(userId=item.finder_id),
            updatedAt=item.updated_at, postedAt=item.posted_at,
            expiresAt=item.expires_at, closedAt=item.closed_at,
        )

    async def page(self, filters, params):
        total = await self.db.scalar(select(func.count()).select_from(FoundItem).where(*filters))
        items = (await self.db.scalars(select(FoundItem).where(*filters).order_by(
            FoundItem.created_at.desc(), FoundItem.id.desc(),
        ).offset(params.page * params.size).limit(params.size))).all()
        return FoundItemPage(
            items=await self.summaries(items), page=params.page, size=params.size,
            totalElements=total, totalPages=(total + params.size - 1) // params.size,
        )

    # ------------------------------------------------------------------- reads

    async def search(self, params):
        """ITEM-01: public list; hidden and deleted posts are never returned."""
        statuses = set(params.statuses) if params.statuses else {'POSTED'}
        filters = [~FoundItem.hidden, FoundItem.deleted_at.is_(None), FoundItem.status.in_(statuses)]

        if params.q:
            # Escape LIKE wildcards so a user typing % or _ searches for the literal text.
            escaped = params.q.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
            pattern = f'%{escaped}%'
            filters.append(or_(
                FoundItem.title.ilike(pattern, escape='\\'),
                FoundItem.description.ilike(pattern, escape='\\'),
            ))
        if params.category_id:
            filters.append(FoundItem.category_id == params.category_id)
        if params.found_building_id:
            filters.append(FoundItem.found_building_id == params.found_building_id)
        # Dates are KST calendar days; the end day is inclusive.
        if params.found_date_from:
            filters.append(FoundItem.found_at >= datetime.combine(params.found_date_from, time.min, tzinfo=KST))
        if params.found_date_to:
            end = params.found_date_to + timedelta(days=1)
            filters.append(FoundItem.found_at < datetime.combine(end, time.min, tzinfo=KST))
        return await self.page(filters, params)

    async def get(self, item_id):
        """ITEM-02: public detail."""
        return await self.detail(await self.load(item_id))

    async def list_mine(self, params):
        """ITEM-10: own posts in every state, hidden ones included; deleted ones never."""
        filters = [FoundItem.finder_id == self.user.id, FoundItem.deleted_at.is_(None)]
        if params.statuses:
            filters.append(FoundItem.status.in_(set(params.statuses)))
        return await self.page(filters, params)

    # ---------------------------------------------------------------- drop-off

    async def latest_version(self, item_id):
        version = await self.db.scalar(select(DropOffVersion).where(
            DropOffVersion.item_id == item_id,
        ).order_by(DropOffVersion.revision_no.desc()).limit(1))
        if version is None:
            raise AuthError(404, 'NOT_FOUND')
        return version

    async def drop_off_responses(self, versions):
        building_ids = {version.building_id for version in versions if version.building_id}
        buildings = {}
        if building_ids:
            buildings = {row.id: row for row in (await self.db.scalars(select(Building).where(
                Building.id.in_(building_ids),
            ))).all()}
        storage = {row.drop_off_version_id: row for row in (await self.db.scalars(
            select(PhotoAttachment).where(
                PhotoAttachment.drop_off_version_id.in_([version.id for version in versions]),
            ),
        )).all()}

        responses = {}
        for version in versions:
            building = buildings.get(version.building_id)
            photo = storage.get(version.id)
            responses[version.id] = DropOffResponse(
                mode=version.mode,
                building=dict(buildingId=building.id, code=building.code, nameKo=building.name_ko,
                              nameEn=building.name_en, active=building.active) if building else None,
                spotDescription=version.spot_description,
                # Storage photos are always login-protected.
                photo=dict(photoId=photo.photo_id, altText=photo.alt_text,
                           accessRequiresLogin=True) if photo else None,
                updatedAt=version.changed_at,
            )
        return responses

    def audit_drop_off_view(self, item, category, versions):
        # Every real read of a sensitive item's storage spot is recorded (FR-7, FR-30).
        if category.sensitive or any(version.sensitive_latched for version in versions):
            append_audit(self.db, self.user, 'SENSITIVE_DROP_OFF_VIEWED', 'FOUND_ITEM',
                         item.id, self.now)

    async def drop_off(self, item_id):
        """ITEM-06: current storage spot (members only)."""
        item = await self.load(item_id)
        category = await self.db.get(Category, item.category_id)
        version = await self.latest_version(item.id)

        response = (await self.drop_off_responses([version]))[version.id]
        self.audit_drop_off_view(item, category, [version])
        # Flush now: if the audit row cannot be stored, nothing is delivered.
        await self.db.flush()
        return response

    async def drop_off_history(self, item_id, params):
        """ITEM-08: newest-first revisions, each with the spot before and after."""
        item = await self.load(item_id)
        category = await self.db.get(Category, item.category_id)

        total = await self.db.scalar(select(func.count()).select_from(DropOffVersion).where(
            DropOffVersion.item_id == item.id,
        ))
        rows = (await self.db.scalars(select(DropOffVersion).where(
            DropOffVersion.item_id == item.id,
        ).order_by(DropOffVersion.revision_no.desc()).offset(params.page * params.size).limit(params.size))).all()

        # The "before" of the oldest row on this page lives on the next page.
        wanted = {row.revision_no - 1 for row in rows if row.revision_no > 1}
        previous = []
        if wanted:
            previous = (await self.db.scalars(select(DropOffVersion).where(
                DropOffVersion.item_id == item.id, DropOffVersion.revision_no.in_(wanted),
            ))).all()
        by_revision = {row.revision_no: row for row in [*rows, *previous]}
        responses = await self.drop_off_responses(list(by_revision.values())) if by_revision else {}

        entries = []
        for row in rows:
            before = by_revision.get(row.revision_no - 1)
            entries.append(DropOffHistoryEntry(
                historyId=row.id, changedByUserId=row.changed_by_user_id, changedAt=row.changed_at,
                before=responses[before.id] if before else None, after=responses[row.id],
            ))

        self.audit_drop_off_view(item, category, list(by_revision.values()))
        await self.db.flush()
        return DropOffHistoryPage(
            items=entries, page=params.page, size=params.size, totalElements=total,
            totalPages=(total + params.size - 1) // params.size,
        )

    async def change_drop_off(self, item_id, body):
        """ITEM-07: append a new revision; history rows are never edited."""
        item = await self.load(item_id, writing=True)
        self.require_finder(item)
        category = await self.db.scalar(select(Category).where(
            Category.id == item.category_id,
        ).with_for_update(read=True))
        current = await self.latest_version(item.id)

        building = None
        if isinstance(body, DropOffLocation):
            building = await self.db.scalar(select(Building).where(
                Building.id == body.building_id,
            ).with_for_update(read=True))
            # An already-used inactive building may stay; a new inactive choice is refused.
            if building is None or (not building.active and building.id != current.building_id):
                raise AuthError(400, 'INVALID_REFERENCE')

        version = DropOffVersion(
            item_id=item.id, revision_no=current.revision_no + 1, mode=body.mode,
            building_id=building.id if building else None,
            spot_description=body.spot_description if building else None,
            changed_by_user_id=self.user.id, changed_at=self.now,
            sensitive_latched=category.sensitive or current.sensitive_latched,
        )
        self.db.add(version)
        await self.db.flush()

        if isinstance(body, DropOffLocation) and body.photo:
            await attach_photo(
                self.db, photo_id=body.photo.photo_id, item=item, user=self.user, now=self.now,
                alt_text=body.photo.alt_text, purpose='DROP_OFF', drop_off_version=version,
            )

        append_audit(self.db, self.user, 'DROP_OFF_CHANGED', 'FOUND_ITEM', item.id, self.now)
        self.audit_drop_off_view(item, category, [version])
        await self.db.flush()
        return (await self.drop_off_responses([version]))[version.id]

    # ---------------------------------------------------------- write follow-up

    async def request_follow_up(self, item, text_changed):
        """Queue analysis (text changed) or just re-evaluation, like the other writers."""
        runtime = await self.db.get(MatchingRuntime, 1)
        if runtime is None or not runtime.active_policy_id:
            return  # analysis is not configured; editing must keep working
        if text_changed:
            await request_found_item_analysis(self.db, item=item, now=self.now)
        else:
            await request_item_reevaluation(self.db, item=item, now=self.now)

    async def replace_photos(self, item, photos):
        current = {row.photo_id: row for row in (await self.db.scalars(select(PhotoAttachment).where(
            PhotoAttachment.item_id == item.id,
            PhotoAttachment.drop_off_version_id.is_(None),
            PhotoAttachment.detached_at.is_(None),
        ).with_for_update())).all()}
        wanted = {photo.photo_id for photo in photos}

        # Detach instead of deleting: the photo keeps its history and protection label.
        for photo_id, row in current.items():
            if photo_id not in wanted:
                row.detached_at = self.now

        # Step kept rows aside so reordering cannot hit the unique (item, order) index.
        kept = [row for photo_id, row in current.items() if photo_id in wanted]
        for row in kept:
            row.display_order += 100
        await self.db.flush()

        for order, photo in enumerate(photos):
            row = current.get(photo.photo_id)
            if row is not None:
                row.display_order = order
                row.alt_text = photo.alt_text
            else:
                await attach_photo(
                    self.db, photo_id=photo.photo_id, item=item, user=self.user, now=self.now,
                    alt_text=photo.alt_text, display_order=order,
                )
        await self.db.flush()

    # ------------------------------------------------------------------ writes

    async def update(self, item_id, body):
        """ITEM-04: change only the supplied fields; status, hidden and storage spot stay."""
        changes = body.model_fields_set
        extra = [body.category_id] if 'category_id' in changes else []
        item = await self.load(item_id, writing=True, extra_categories=extra)
        self.require_finder(item)

        if 'found_at' in changes and body.found_at > self.now:
            raise AuthError(400, 'VALIDATION_ERROR', fields=[
                {'field': 'foundAt', 'code': 'INVALID_FORMAT'},
            ])
        # Keeping an existing inactive reference is fine; choosing a new inactive one is not.
        if 'category_id' in changes and body.category_id != item.category_id:
            category = await self.db.scalar(select(Category).where(
                Category.id == body.category_id,
            ).with_for_update(read=True))
            if category is None or not category.active:
                raise AuthError(400, 'INVALID_REFERENCE')
        if 'found_building_id' in changes and body.found_building_id != item.found_building_id:
            building = await self.db.scalar(select(Building).where(
                Building.id == body.found_building_id,
            ).with_for_update(read=True))
            if building is None or not building.active:
                raise AuthError(400, 'INVALID_REFERENCE')

        text_changed = any(
            name in changes and getattr(body, name) != getattr(item, name)
            for name in ('title', 'description')
        )
        for name in changes - {'photos'}:
            setattr(item, name, getattr(body, name))
        item.updated_at = self.now
        flag_modified(item, 'updated_at')
        await self.db.flush()

        if 'photos' in changes:
            await self.replace_photos(item, body.photos)

        await self.db.flush()
        await self.db.refresh(item)
        await self.request_follow_up(item, text_changed)
        return await self.detail(item)

    async def delete(self, item_id):
        """ITEM-05: logical delete. DB triggers drop candidates, analysis and conversations."""
        item = await self.load(item_id, writing=True)
        self.require_finder(item)

        item.deleted_at = self.now
        # A closed item keeps its original retention date; an open one starts at deletion.
        if item.purge_after is None:
            item.purge_after = one_year_after(item.closed_at or self.now)
        item.updated_at = self.now
        flag_modified(item, 'updated_at')
        await self.db.flush()

    async def repost(self, item_id):
        """ITEM-09: EXPIRED -> POSTED with a fresh 30-day window; hidden stays as it was."""
        item = await self.load(item_id, writing=True)
        self.require_finder(item)
        if item.status != 'EXPIRED':
            raise AuthError(409, 'ITEM_NOT_EXPIRED')

        item.status = 'POSTED'
        item.posted_at = self.now
        item.expires_at = self.now + timedelta(days=30)
        item.closed_at = None
        item.purge_after = None
        item.updated_at = self.now
        flag_modified(item, 'updated_at')
        await self.db.flush()

        append_audit(self.db, self.user, 'ITEM_STATUS_CHANGED', 'FOUND_ITEM', item.id, self.now,
                     fromStatus='EXPIRED', toStatus='POSTED')
        await self.db.refresh(item)
        await self.request_follow_up(item, text_changed=False)
        return await self.detail(item)
