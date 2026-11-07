"""Collection disputes within the protected request transaction."""

from sqlalchemy import func, select

from model import Collection, Dispute, FoundItem
from schema.disputes import DisputePage, DisputeResponse
from service.auth import AuthError


def dispute_response(row, item_id):
    return DisputeResponse(
        disputeId=row.id, itemId=item_id, collectionId=row.collection_id,
        reason=row.reason, status=row.status, decision=row.decision,
        createdAt=row.created_at, resolvedAt=row.resolved_at,
    )


class DisputeService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user
        self.now = request.state.now

    async def item(self, item_id, *, writing=False):
        query = select(FoundItem).where(FoundItem.id == item_id)
        if writing:
            # Collection creation/cancellation must also lock the item first.
            query = query.with_for_update()
        item = await self.db.scalar(query)
        if item is None or item.deleted_at is not None:
            raise AuthError(404, 'NOT_FOUND')

        if item.finder_id != self.user.id:
            if writing:
                raise AuthError(403, 'FINDER_ONLY')
            if self.user.role != 'ADMIN':
                raise AuthError(403, 'FORBIDDEN')
        return item

    async def create(self, item_id, reason):
        item = await self.item(item_id, writing=True)
        if item.status != 'COLLECTED':
            raise AuthError(409, 'ITEM_NOT_COLLECTED')

        collection = await self.db.scalar(select(Collection).where(
            Collection.item_id == item.id, Collection.undone_at.is_(None),
        ).with_for_update())
        if collection is None:
            raise AuthError(409, 'ITEM_NOT_COLLECTED')

        existing = await self.db.scalar(select(Dispute.id).where(
            Dispute.collection_id == collection.id, Dispute.status == 'OPEN',
        ))
        if existing is not None:
            raise AuthError(409, 'OPEN_DISPUTE_EXISTS')

        row = Dispute(
            collection_id=collection.id, reason=reason, status='OPEN',
            created_at=self.now, purge_after=collection.purge_after,
        )
        self.db.add(row)
        await self.db.flush()
        return dispute_response(row, item.id)

    async def list(self, item_id, params):
        item = await self.item(item_id)
        query = select(Dispute).join(Collection).where(Collection.item_id == item.id)
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.db.scalars(query.order_by(
            Dispute.created_at.desc(), Dispute.id.desc(),
        ).offset(params.page * params.size).limit(params.size))

        return DisputePage(
            items=[dispute_response(row, item.id) for row in rows],
            page=params.page, size=params.size,
            totalElements=total, totalPages=(total + params.size - 1) // params.size,
        )
