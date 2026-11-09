"""Latest evidence and collection side effects share one transaction."""

from types import SimpleNamespace

import pytest
from sqlalchemy import select

from model import Collection, FoundItem, LostReport, LostReportPrivateDetail, User
from service.auth import AuthError
from service.collections import CollectionService
from test_analysis_worker import analysis_env
from test_matching_service import setup


@pytest.mark.asyncio
async def test_latest_evidence_resolves_without_saved_candidates(analysis_env):
    env = analysis_env
    await setup(env)
    async with env.factory() as db, db.begin():
        report = await db.get(LostReport, env.ids['report'])
        user = await db.get(User, report.owner_id)
        request = SimpleNamespace(state=SimpleNamespace(db=db, user=user, now=env.clock()))
        result = await CollectionService(request).collect(env.ids['item'])
        assert result.collector_id == user.id
    async with env.factory() as db:
        assert (await db.get(LostReport, env.ids['report'])).status == 'RESOLVED'
        assert await db.get(LostReportPrivateDetail, env.ids['report']) is None
        assert (await db.get(FoundItem, env.ids['item'])).status == 'COLLECTED'


@pytest.mark.asyncio
async def test_pending_analysis_rolls_back_all_changes(analysis_env):
    env = analysis_env
    await setup(env, ready=False)
    with pytest.raises(AuthError) as caught:
        async with env.factory() as db, db.begin():
            report = await db.get(LostReport, env.ids['report'])
            user = await db.get(User, report.owner_id)
            request = SimpleNamespace(state=SimpleNamespace(db=db, user=user, now=env.clock()))
            await CollectionService(request).collect(env.ids['item'])
    assert caught.value.code == 'MATCHING_PENDING'
    async with env.factory() as db:
        assert (await db.get(LostReport, env.ids['report'])).status == 'OPEN'
        assert await db.get(LostReportPrivateDetail, env.ids['report']) is not None
        assert await db.scalar(select(Collection.id).where(Collection.item_id == env.ids['item'])) is None
