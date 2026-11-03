"""Admin transactions use the session and authorization supplied by ProtectedRoute."""
from sqlalchemy import func, select

from model import (AuditLog, Building, Category, Collection, CollectionRestriction,
                   Dispute, FoundItem, PostReport, User)
from service.audit import append_audit
from service.auth import AuthError


def values(row, *names, **extra):
    return {**{name: getattr(row, name) for name in names}, **extra}


def post_response(row):
    return values(row, 'item_id', 'reporter_id', 'reason_code', 'details', 'status',
                  'decision', 'created_at', 'reviewed_at', 'reviewer_id', report_id=row.id)


def dispute_response(row, collection):
    return values(row, 'collection_id', 'reason', 'status', 'decision', 'created_at',
                  'resolved_at', dispute_id=row.id, item_id=collection.item_id,
                  finder_id=collection.finder_id, collector_id=collection.collector_id)


def reference_response(row):
    result = values(row, 'name_ko', 'name_en', 'active')
    if isinstance(row, Building):
        return dict(result, building_id=row.id, code=row.code)
    return dict(result, category_id=row.id, sensitive=row.sensitive)


class AdminService:
    def __init__(self, request):
        self.db, self.actor, self.now = request.state.db, request.state.user, request.state.now

    def audit(self, action, kind, target, **metadata):
        append_audit(self.db, self.actor, action, kind, target, self.now, **metadata)

    async def get(self, model, key, *, lock=False):
        row = await self.db.get(model, key, with_for_update=lock)
        if row is None:
            raise AuthError(404, 'NOT_FOUND')
        return row

    async def page(self, query, params, convert):
        total = await self.db.scalar(select(func.count()).select_from(query.order_by(None).subquery()))
        rows = (await self.db.execute(query.offset(params.page * params.size).limit(params.size))).all()
        return dict(items=[convert(*row) for row in rows], page=params.page, size=params.size,
                    total_elements=total, total_pages=(total + params.size - 1) // params.size)

    async def user_response(self, user):
        restricted = await self.db.get(CollectionRestriction, user.id)
        return values(user, 'name', 'affiliation', 'role', user_id=user.id,
                      collection_restricted=bool(restricted and restricted.restricted))

    async def users(self, params):
        query = select(User, func.coalesce(CollectionRestriction.restricted, False)).outerjoin(
            CollectionRestriction, CollectionRestriction.user_id == User.id)
        if params.q is not None:
            query = query.where(User.name.contains(params.q, autoescape=True))
        if params.role is not None:
            query = query.where(User.role == params.role)
        return await self.page(query.order_by(User.id), params,
            lambda u, restricted: values(u, 'name', 'affiliation', 'role', user_id=u.id,
                                          collection_restricted=restricted))

    async def role(self, user_id, body):
        user = await self.get(User, user_id, lock=True)
        if user.role != body.role:
            if user.role == 'ADMIN' and body.role == 'MEMBER':
                count = await self.db.scalar(select(func.count()).select_from(User).where(User.role == 'ADMIN'))
                if count <= 1:
                    raise AuthError(409, 'LAST_ADMIN')
            self.audit('ROLE_CHANGED', 'USER', user.id, fromRole=user.role, toRole=body.role.value)
            user.role = body.role.value
            await self.db.flush()
        return await self.user_response(user)

    async def references(self, model, params):
        query = select(model)
        if params.active is not None:
            query = query.where(model.active == params.active)
        return await self.page(query.order_by(model.code if model is Building else model.id), params,
                               reference_response)

    async def create_reference(self, model, body):
        data = body.model_dump(by_alias=False)
        if model is Building:
            data['code'] = data['code'].upper()
        row = model(**data, active=True, created_at=self.now, updated_at=self.now)
        self.db.add(row)
        await self.db.flush()
        self.audit('REFERENCE_CREATED', 'BUILDING' if model is Building else 'CATEGORY', row.id)
        return reference_response(row)

    async def update_reference(self, model, key, body):
        row = await self.get(model, key, lock=True)
        data = body.model_dump(exclude_unset=True, by_alias=False)
        if any(getattr(row, key) != value for key, value in data.items()):
            for key, value in data.items():
                setattr(row, key, value)
            row.updated_at = self.now
            self.audit('REFERENCE_UPDATED', 'BUILDING' if model is Building else 'CATEGORY', row.id)
            await self.db.flush()
        return reference_response(row)

    async def reports(self, params):
        query = select(PostReport)
        if params.status is not None:
            query = query.where(PostReport.status == params.status)
        if params.item_id is not None:
            query = query.where(PostReport.item_id == params.item_id)
        return await self.page(query.order_by(PostReport.created_at.desc(), PostReport.id.desc()), params, post_response)

    async def report(self, key):
        return post_response(await self.get(PostReport, key))

    async def create_report(self, item_id, body):
        item = await self.get(FoundItem, item_id, lock=True)
        if item.deleted_at is not None or (item.hidden and self.actor.role != 'ADMIN' and item.finder_id != self.actor.id):
            raise AuthError(404, 'NOT_FOUND')
        row = PostReport(item_id=item_id, reporter_id=self.actor.id, **body.model_dump(by_alias=False),
                         status='OPEN', created_at=self.now)
        self.db.add(row)
        await self.db.flush()
        return post_response(row)

    async def review_report(self, key, body):
        # Item first, then report: matches creation and future item mutation paths.
        snapshot = await self.get(PostReport, key)
        item = await self.get(FoundItem, snapshot.item_id, lock=True)
        row = await self.db.scalar(select(PostReport).where(PostReport.id == key)
                                  .with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise AuthError(404, 'NOT_FOUND')
        if row.status != 'OPEN':
            raise AuthError(409, 'REPORT_ALREADY_REVIEWED')
        if body.decision == 'HIDE' and not item.hidden:
            item.hidden = True
            self.audit('POST_HIDDEN', 'FOUND_ITEM', item.id, reportId=row.id)
        row.status, row.decision = 'REVIEWED', body.decision
        row.reviewed_at, row.reviewer_id = self.now, self.actor.id
        self.audit('POST_REPORT_REVIEWED', 'POST_REPORT', row.id, decision=body.decision)
        await self.db.flush()
        return post_response(row)

    async def disputes(self, params):
        query = select(Dispute, Collection).join(Collection, Dispute.collection_id == Collection.id)
        if params.status is not None:
            query = query.where(Dispute.status == params.status)
        if params.item_id is not None:
            query = query.where(Collection.item_id == params.item_id)
        return await self.page(query.order_by(Dispute.created_at.desc(), Dispute.id.desc()), params, dispute_response)

    async def dispute(self, key):
        row = await self.get(Dispute, key)
        return dispute_response(row, await self.get(Collection, row.collection_id))

    async def restriction(self, user_id, restricted, dispute_id=None):
        # All collection/restriction writers must lock this same user, even without a restriction row.
        await self.get(User, user_id, lock=True)
        if dispute_id is not None:
            dispute = await self.get(Dispute, dispute_id, lock=True)
            collection = await self.get(Collection, dispute.collection_id)
            if dispute.status != 'RESOLVED' or dispute.decision != 'UPHELD':
                raise AuthError(409, 'DISPUTE_NOT_UPHELD')
            if collection.collector_id != user_id:
                raise AuthError(409, 'COLLECTOR_MISMATCH')
        row = await self.db.get(CollectionRestriction, user_id)
        if row is None:
            row = CollectionRestriction(user_id=user_id, restricted=restricted,
                source_dispute_id=dispute_id, updated_by_user_id=self.actor.id, updated_at=self.now)
            self.db.add(row)
            changed = True
        else:
            changed = row.restricted != restricted or (dispute_id is not None and row.source_dispute_id != dispute_id)
            if changed:
                row.restricted = restricted
                if dispute_id is not None:
                    row.source_dispute_id = dispute_id
                row.updated_at, row.updated_by_user_id = self.now, self.actor.id
        if changed:
            metadata = dict(restricted=restricted)
            if row.source_dispute_id is not None:
                metadata['disputeId'] = row.source_dispute_id
            self.audit('COLLECTION_RESTRICTION_CHANGED', 'USER', user_id, **metadata)
        await self.db.flush()
        await self.db.refresh(row)
        return values(row, 'user_id', 'restricted', 'updated_at', dispute_id=row.source_dispute_id)

    async def review_dispute(self, key, body):
        if body.decision == 'DISMISSED' and body.block_collector:
            raise AuthError(400, 'INVALID_DECISION')
        snapshot = await self.get(Dispute, key)
        collection = await self.get(Collection, snapshot.collection_id)
        # Common user -> dispute order also used by restriction updates.
        await self.get(User, collection.collector_id, lock=True)
        row = await self.db.scalar(select(Dispute).where(Dispute.id == key)
                                  .with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise AuthError(404, 'NOT_FOUND')
        if row.status != 'OPEN':
            raise AuthError(409, 'DISPUTE_ALREADY_RESOLVED')
        row.status, row.decision = 'RESOLVED', body.decision
        row.resolved_at, row.reviewer_id = self.now, self.actor.id
        self.audit('DISPUTE_REVIEWED', 'DISPUTE', row.id, decision=body.decision)
        if body.block_collector:
            await self.restriction(collection.collector_id, True, row.id)
        await self.db.flush()
        return dispute_response(row, collection)

    async def statistics(self):
        counts = dict((await self.db.execute(select(FoundItem.status, func.count()).where(
            FoundItem.deleted_at.is_(None)).group_by(FoundItem.status))).all())
        return dict(posted_count=counts.get('POSTED', 0), collected_count=counts.get('COLLECTED', 0),
                    expired_count=counts.get('EXPIRED', 0), as_of=self.now)

    async def audits(self, params):
        if params.from_time and params.to_time and params.from_time >= params.to_time:
            raise AuthError(400, 'INVALID_TIME_RANGE')
        query = select(AuditLog)
        for name in ('actor_id', 'target_id', 'action'):
            value = getattr(params, name)
            if value is not None:
                query = query.where(getattr(AuditLog, name) == value)
        if params.from_time is not None:
            query = query.where(AuditLog.occurred_at >= params.from_time)
        if params.to_time is not None:
            query = query.where(AuditLog.occurred_at < params.to_time)
        return await self.page(query.order_by(AuditLog.occurred_at.desc(), AuditLog.id.desc()), params,
            lambda row: values(row, 'actor_id', 'actor_type', 'action', 'target_type', 'target_id',
                               'occurred_at', audit_log_id=row.id, metadata=row.event_metadata))
