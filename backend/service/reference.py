"""Active public reference lists and current drop-off counts."""

from sqlalchemy import func, select

from model import Building, Category, DropOffVersion, FoundItem
from schema.reference import (
    BuildingCountSummary,
    BuildingListResponse,
    CategoryListResponse,
    CategorySummary,
)


class ReferenceService:
    def __init__(self, db):
        self.db = db

    async def buildings(self, include_posted_count):
        query = select(Building).where(Building.active.is_(True))
        if include_posted_count:
            latest = select(
                DropOffVersion.item_id,
                DropOffVersion.building_id,
                DropOffVersion.mode,
                func.row_number().over(
                    partition_by=DropOffVersion.item_id,
                    order_by=DropOffVersion.revision_no.desc(),
                ).label('position'),
            ).subquery()
            counts = select(
                latest.c.building_id,
                func.count().label('posted_count'),
            ).join(FoundItem, FoundItem.id == latest.c.item_id).where(
                latest.c.position == 1,
                latest.c.mode == 'DROP_OFF',
                FoundItem.status == 'POSTED',
                FoundItem.hidden.is_(False),
                FoundItem.deleted_at.is_(None),
            ).group_by(latest.c.building_id).subquery()
            query = query.outerjoin(counts, counts.c.building_id == Building.id).add_columns(
                func.coalesce(counts.c.posted_count, 0),
            )

        rows = await self.db.execute(query.order_by(Building.created_at.desc(), Building.id.desc()))
        items = []
        for row in rows:
            building = row[0]
            payload = dict(
                buildingId=building.id, code=building.code,
                nameKo=building.name_ko, nameEn=building.name_en, active=building.active,
            )
            if include_posted_count:
                payload['postedCount'] = row[1]
            items.append(BuildingCountSummary.model_validate(payload))

        return BuildingListResponse(items=items)

    async def categories(self):
        rows = await self.db.scalars(
            select(Category).where(Category.active.is_(True)).order_by(
                Category.created_at.desc(), Category.id.desc(),
            ),
        )
        return CategoryListResponse(items=[
            CategorySummary(
                categoryId=row.id, nameKo=row.name_ko, nameEn=row.name_en,
                active=row.active, sensitive=row.sensitive,
            )
            for row in rows
        ])
