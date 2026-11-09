"""Collection mutations share the protected request transaction."""

from datetime import timedelta

from sqlalchemy import delete, select

from library.matching_lock import lock_matching_categories
from library.text_analysis_types import AnalysisError
from model import (
    Collection, CollectionRestriction, Conversation, FoundItem, FoundItemTextFeature,
    LostReport, LostReportBuilding, LostReportPrivateDetail, LostReportTextFeature,
    MatchingRuntime, User,
)
from schema.collections import CollectionResponse
from service.audit import append_audit, one_year_after
from service.auth import AuthError
from service.matching import KST, candidate_evidence
from service.text_analysis import request_item_reevaluation
from service.text_analysis_profiles import active_policy


def response(row):
    return CollectionResponse(
        collectionId=row.id, itemId=row.item_id, collectorId=row.collector_id,
        collectedAt=row.collected_at,
    )


class CollectionService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user
        self.now = request.state.now

    async def item(self, item_id, *, writing=False, collecting=False):
        category = await self.db.scalar(select(FoundItem.category_id).where(FoundItem.id == item_id))
        if category is None:
            raise AuthError(404, 'NOT_FOUND')
        if writing:
            await lock_matching_categories(self.db, [category])
            if collecting:
                await self.db.scalar(select(User).where(User.id == self.user.id).with_for_update())
        query = select(FoundItem).where(FoundItem.id == item_id).execution_options(populate_existing=True)
        item = await self.db.scalar(query.with_for_update() if writing else query)
        if item is None or item.deleted_at is not None or (collecting and item.hidden):
            raise AuthError(404, 'NOT_FOUND')
        if writing and item.category_id != category:
            raise AuthError(409, 'CONCURRENT_MODIFICATION')
        return item

    async def current(self, item, *, writing=False):
        query = select(Collection).where(Collection.item_id == item.id, Collection.undone_at.is_(None))
        row = await self.db.scalar(query.with_for_update() if writing else query)
        if self.user.role != 'ADMIN' and self.user.id not in {
            item.finder_id, row.collector_id if row else None,
        }:
            raise AuthError(403, 'FORBIDDEN')
        return row

    async def get(self, item_id):
        row = await self.current(await self.item(item_id))
        if row is None:
            raise AuthError(404, 'COLLECTION_NOT_FOUND')
        return response(row)

    async def resolve_reports(self, item):
        reports = list(await self.db.scalars(select(LostReport).where(
            LostReport.owner_id == self.user.id, LostReport.category_id == item.category_id,
            LostReport.status == 'OPEN', LostReport.expires_at > self.now,
            LostReport.lost_date_from <= item.found_at.astimezone(KST).date(),
        ).order_by(LostReport.id).with_for_update()))
        if not reports:
            return

        try:
            _, profile = await active_policy(self.db)
        except AnalysisError:
            raise AuthError(409, 'MATCHING_PENDING') from None
        item_feature = await self.db.scalar(select(FoundItemTextFeature).where(
            FoundItemTextFeature.item_id == item.id,
            FoundItemTextFeature.profile_id == profile.id,
            FoundItemTextFeature.text_version == item.text_version,
        ))
        for report in reports:
            feature = await self.db.scalar(select(LostReportTextFeature).where(
                LostReportTextFeature.report_id == report.id,
                LostReportTextFeature.profile_id == profile.id,
                LostReportTextFeature.text_version == report.text_version,
            ))
            if any(f is None or f.status != 'READY' for f in (item_feature, feature)):
                raise AuthError(409, 'MATCHING_PENDING')
            buildings = set(await self.db.scalars(select(LostReportBuilding.building_id).where(
                LostReportBuilding.report_id == report.id,
            )))
            building, keywords = candidate_evidence(item, report, buildings, item_feature, feature)
            if not building and not keywords:
                continue

            report.status = 'RESOLVED'
            report.closed_at = self.now
            report.purge_after = one_year_after(self.now)
            await self.db.execute(delete(LostReportPrivateDetail).where(
                LostReportPrivateDetail.report_id == report.id,
            ))
            append_audit(
                self.db, self.user, 'LOST_REPORT_STATUS_CHANGED', 'LOST_REPORT', report.id,
                self.now, fromStatus='OPEN', toStatus='RESOLVED',
            )

    async def collect(self, item_id):
        item = await self.item(item_id, writing=True, collecting=True)
        restriction = await self.db.get(CollectionRestriction, self.user.id)
        if restriction and restriction.restricted:
            raise AuthError(403, 'COLLECTION_RESTRICTED')
        if item.status == 'COLLECTED':
            raise AuthError(409, 'ALREADY_COLLECTED')
        if item.status != 'POSTED':
            raise AuthError(409, 'ITEM_NOT_POSTED')

        await self.resolve_reports(item)
        row = Collection(
            item_id=item.id, finder_id=item.finder_id, collector_id=self.user.id,
            collected_at=self.now, purge_after=one_year_after(self.now),
        )
        self.db.add(row)
        item.status = 'COLLECTED'
        item.closed_at = self.now
        item.purge_after = one_year_after(self.now)
        await self.db.execute(delete(Conversation).where(Conversation.item_id == item.id))
        await self.db.flush()
        append_audit(
            self.db, self.user, 'COLLECTION_MARKED', 'COLLECTION', row.id, self.now,
            collectionId=row.id,
        )
        append_audit(
            self.db, self.user, 'ITEM_STATUS_CHANGED', 'FOUND_ITEM', item.id, self.now,
            fromStatus='POSTED', toStatus='COLLECTED', collectionId=row.id,
        )
        # The collection INSERT trigger atomically schedules its notification outbox.
        return response(row)

    async def cancel(self, item_id):
        item = await self.item(item_id, writing=True)
        row = await self.current(item, writing=True)
        if item.status != 'COLLECTED' or row is None:
            raise AuthError(409, 'ITEM_NOT_COLLECTED')

        row.undone_at = self.now
        row.undone_by_user_id = self.user.id
        item.status = 'POSTED'
        item.posted_at = self.now
        item.expires_at = self.now + timedelta(days=30)
        item.closed_at = None
        item.purge_after = None
        append_audit(
            self.db, self.user, 'COLLECTION_UNDONE', 'COLLECTION', row.id, self.now,
            collectionId=row.id,
        )
        append_audit(
            self.db, self.user, 'ITEM_STATUS_CHANGED', 'FOUND_ITEM', item.id, self.now,
            fromStatus='COLLECTED', toStatus='POSTED', collectionId=row.id,
        )
        # No policy means analysis is not configured; cancellation remains available.
        runtime = await self.db.get(MatchingRuntime, 1)
        if runtime and runtime.active_policy_id:
            await request_item_reevaluation(self.db, item=item, now=self.now)
