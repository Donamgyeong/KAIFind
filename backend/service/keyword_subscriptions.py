"""Owner-scoped subscriptions; inference is performed outside DB transactions."""

import unicodedata

from sqlalchemy import func, select, true
from sqlalchemy.orm import aliased

from library.keyword_subscription_matching import SUBSCRIPTION_RULE
from model import KeywordSubscription, KeywordSubscriptionFeature, MatchingRuntime, User
from schema.keyword_subscriptions import KeywordSubscriptionPage, KeywordSubscriptionResponse
from service.auth import AuthError
from service.text_analysis_profiles import active_policy


def normalized_keyword(value):
    return unicodedata.normalize('NFKC', value).lower()


def response(row):
    return KeywordSubscriptionResponse(subscriptionId=row.id, keyword=row.keyword, createdAt=row.created_at)


class KeywordSubscriptionService:
    def __init__(self, request):
        self.db, self.user, self.now = request.state.db, request.state.user, request.state.now

    async def check_duplicate(self, keyword):
        exists = await self.db.scalar(select(KeywordSubscription.id).where(
            KeywordSubscription.user_id == self.user.id,
            KeywordSubscription.normalized_keyword == normalized_keyword(keyword),
        ))
        if exists is not None:
            raise AuthError(409, 'KEYWORD_ALREADY_SUBSCRIBED')

    async def create(self, body, analysis, terms, profile_id, runtime_profile):
        # Serialize with profile activation and user deletion/notification delivery.
        await self.db.scalar(select(MatchingRuntime).where(MatchingRuntime.id == 1).with_for_update())
        _, profile = await active_policy(self.db, runtime_profile)
        if profile.id != profile_id or analysis.profile_fingerprint != profile.fingerprint:
            raise AuthError(503, 'KEYWORD_ANALYSIS_UNAVAILABLE', headers={'Retry-After': '5'})
        await self.db.scalar(select(User).where(User.id == self.user.id).with_for_update())
        await self.check_duplicate(body.keyword)

        row = KeywordSubscription(user_id=self.user.id, keyword=body.keyword,
                                  normalized_keyword=normalized_keyword(body.keyword))
        self.db.add(row)
        await self.db.flush()
        await self.db.refresh(row)
        self.db.add(KeywordSubscriptionFeature(
            subscription_id=row.id, profile_id=profile.id, rule_version=SUBSCRIPTION_RULE,
            status='READY', terms=list(terms), source_hash=analysis.source_hash, completed_at=self.now,
        ))
        await self.db.flush()
        return response(row)

    async def list(self, params):
        filtered = select(KeywordSubscription).where(
            KeywordSubscription.user_id == self.user.id,
        ).cte('keyword_filtered')
        total = select(func.count().label('total')).select_from(filtered).cte('keyword_total')
        page = select(filtered).order_by(filtered.c.created_at.desc(), filtered.c.id.desc()).offset(
            params.page * params.size,
        ).limit(params.size).cte('keyword_page')
        entity = aliased(KeywordSubscription, page)
        rows = (await self.db.execute(select(total.c.total, entity).select_from(
            total.outerjoin(page, true()),
        ).order_by(page.c.created_at.desc(), page.c.id.desc()))).all()
        count = rows[0][0]
        return KeywordSubscriptionPage(
            items=[response(row) for _, row in rows if row is not None],
            page=params.page, size=params.size, totalElements=count,
            totalPages=(count + params.size - 1) // params.size,
        )

    async def delete(self, subscription_id):
        await self.db.scalar(select(User).where(User.id == self.user.id).with_for_update())
        row = await self.db.scalar(select(KeywordSubscription).where(
            KeywordSubscription.id == subscription_id, KeywordSubscription.user_id == self.user.id,
        ).with_for_update())
        if row is None:
            raise AuthError(404, 'KEYWORD_SUBSCRIPTION_NOT_FOUND')
        await self.db.delete(row)
