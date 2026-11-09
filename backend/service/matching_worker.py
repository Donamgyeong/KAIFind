"""Durable generation consumer. Candidate writes are fenced by category and lease."""
import asyncio
from contextlib import suppress
from datetime import timedelta
import logging
import random
from uuid import uuid4

from sqlalchemy import or_, select, update
from sqlalchemy.dialects.postgresql import insert

from library.matching_lock import lock_matching_categories
from library.text_analysis_types import AnalysisError
from model import (
    FoundItem, FoundItemTextFeature, LostReport, LostReportBuilding,
    LostReportTextFeature, MatchCandidate, MatchEvaluationJob,
)
from service.matching import KST, candidate_evidence
from service.notification_events import create_notification
from service.outbox_worker import utcnow
from service.text_analysis import eligible
from service.text_analysis_profiles import active_policy


logger = logging.getLogger(__name__)


class MatchingWorker:
    def __init__(self, factory, *, clock=utcnow, lease_seconds=60, max_attempts=5, poll_seconds=1):
        if lease_seconds <= 0 or max_attempts < 1 or poll_seconds <= 0:
            raise ValueError('Invalid matching worker limits')
        self.factory = factory
        self.clock = clock
        self.lease_seconds = lease_seconds
        self.max_attempts = max_attempts
        self.poll_seconds = poll_seconds
        self.stop = asyncio.Event()
        self.task = None

    async def claim(self):
        async with self.factory() as db, db.begin():
            now = self.clock()
            job = (await db.execute(select(MatchEvaluationJob).where(
                MatchEvaluationJob.completed_generation < MatchEvaluationJob.requested_generation,
                MatchEvaluationJob.failed_at.is_(None), MatchEvaluationJob.next_attempt_at <= now,
                or_(MatchEvaluationJob.lease_until.is_(None), MatchEvaluationJob.lease_until <= now),
            ).order_by(MatchEvaluationJob.next_attempt_at, MatchEvaluationJob.id)
                .with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
            if job is None:
                return None
            job.claimed_generation = job.requested_generation
            job.lease_token = uuid4()
            job.lease_until = now + timedelta(seconds=self.lease_seconds)
            return job

    def fence(self, job):
        return (
            MatchEvaluationJob.id == job.id, MatchEvaluationJob.lease_token == job.lease_token,
            MatchEvaluationJob.claimed_generation == job.claimed_generation,
            MatchEvaluationJob.lease_until > self.clock(), MatchEvaluationJob.failed_at.is_(None),
        )

    async def heartbeat(self, job):
        while True:
            await asyncio.sleep(self.lease_seconds / 3)
            async with self.factory() as db, db.begin():
                result = await db.execute(update(MatchEvaluationJob).where(*self.fence(job)).values(
                    lease_until=self.clock() + timedelta(seconds=self.lease_seconds),
                ))
                if result.rowcount != 1:
                    return

    async def workset(self, db, job):
        """Read IDs/categories without owner row locks, including obsolete links."""
        model = FoundItem if job.item_id is not None else LostReport
        owner_id = job.item_id if job.item_id is not None else job.report_id
        owner = (await db.execute(select(model.id, model.category_id).where(model.id == owner_id))).first()
        if owner is None:
            return {}, {}

        if job.item_id is not None:
            reports = (await db.execute(select(LostReport.id, LostReport.category_id).where(or_(
                LostReport.category_id == owner.category_id,
                LostReport.id.in_(select(MatchCandidate.report_id).where(MatchCandidate.item_id == owner_id)),
            )))).all()
            return {owner.id: owner.category_id}, dict(reports)
        items = (await db.execute(select(FoundItem.id, FoundItem.category_id).where(or_(
            FoundItem.category_id == owner.category_id,
            FoundItem.id.in_(select(MatchCandidate.item_id).where(MatchCandidate.report_id == owner_id)),
        )))).all()
        return dict(items), {owner.id: owner.category_id}

    async def evaluate(self, db, job):
        before_items, before_reports = await self.workset(db, job)
        categories = set(before_items.values()) | set(before_reports.values())
        await lock_matching_categories(db, categories)
        item_ids, report_ids = await self.workset(db, job)
        if (item_ids != before_items or report_ids != before_reports):
            raise AnalysisError('CONCURRENT_MODIFICATION', retryable=True)

        items = (await db.scalars(select(FoundItem).where(FoundItem.id.in_(item_ids))
            .order_by(FoundItem.id).with_for_update())).all()
        reports = (await db.scalars(select(LostReport).where(LostReport.id.in_(report_ids))
            .order_by(LostReport.id).with_for_update())).all()
        if (any(i.category_id != item_ids[i.id] for i in items)
                or any(r.category_id != report_ids[r.id] for r in reports)):
            raise AnalysisError('CONCURRENT_MODIFICATION', retryable=True)

        policy, profile = await active_policy(db)
        current = (await db.execute(select(MatchEvaluationJob).where(*self.fence(job)))).scalar_one_or_none()
        if current is None:
            return
        now = self.clock()
        owner = next((o for o in (items if job.item_id is not None else reports)
                      if o.id == (job.item_id or job.report_id)), None)
        if owner is None or not eligible(owner, now) or policy.id != job.policy_id:
            await self.finish(db, job, now, complete=True)
            return

        item_features = {f.item_id: f for f in (await db.scalars(select(FoundItemTextFeature).where(
            FoundItemTextFeature.item_id.in_([i.id for i in items]),
            FoundItemTextFeature.profile_id == profile.id,
            FoundItemTextFeature.text_version.in_([i.text_version for i in items]),
        ))).all() if any(i.id == f.item_id and i.text_version == f.text_version for i in items)}
        report_features = {f.report_id: f for f in (await db.scalars(select(LostReportTextFeature).where(
            LostReportTextFeature.report_id.in_([r.id for r in reports]),
            LostReportTextFeature.profile_id == profile.id,
            LostReportTextFeature.text_version.in_([r.text_version for r in reports]),
        ))).all() if any(r.id == f.report_id and r.text_version == f.text_version for r in reports)}
        buildings = {}
        for report_id, building_id in (await db.execute(select(
            LostReportBuilding.report_id, LostReportBuilding.building_id,
        ).where(LostReportBuilding.report_id.in_([r.id for r in reports])))).all():
            buildings.setdefault(report_id, set()).add(building_id)

        waiting = False
        for report in reports:
            if not eligible(report, now):
                continue
            for item in items:
                # Each job has exactly one owner, so this is one row or one column.
                fi, fr = item_features.get(item.id), report_features.get(report.id)
                building, keywords = candidate_evidence(item, report, buildings.get(report.id, set()), fi, fr)
                in_scope = (item.deleted_at is None and item.category_id == report.category_id
                            and item.found_at.astimezone(KST).date()
                            >= report.lost_date_from)
                if in_scope:
                    waiting |= any(f is None or f.status in {'PENDING', 'PROCESSING', 'SUPERSEDED'} for f in (fi, fr))
                await self.save_candidate(db, item, report, policy, profile, fi, fr, building, keywords, now)

        # Even an empty comparison range requires the owner's current analysis.
        own_feature = (item_features if job.item_id is not None else report_features).get(owner.id)
        waiting |= own_feature is None or own_feature.status in {'PENDING', 'PROCESSING', 'SUPERSEDED'}
        await self.finish(db, job, self.clock(), complete=not waiting)

    async def save_candidate(self, db, item, report, policy, profile, fi, fr, building, keywords, now):
        if not building and not keywords:
            await db.execute(update(MatchCandidate).where(
                MatchCandidate.item_id == item.id, MatchCandidate.report_id == report.id,
            ).values(active=False, last_evaluated_at=now))
            return

        values = dict(
            active=True, building_matched=building, keyword_matched=bool(keywords),
            policy_id=policy.id, analysis_profile_id=profile.id,
            evaluated_item_version=item.version, evaluated_report_version=report.version,
            item_feature_id=fi.id if keywords else None, report_feature_id=fr.id if keywords else None,
            common_keywords=list(keywords), last_evaluated_at=now,
        )
        await db.execute(insert(MatchCandidate).values(
            report_id=report.id, item_id=item.id, matched_at=now, **values,
        ).on_conflict_do_update(index_elements=['report_id', 'item_id'], set_=values))

        candidate = await db.scalar(select(MatchCandidate).where(
            MatchCandidate.item_id == item.id, MatchCandidate.report_id == report.id,
        ).with_for_update())
        if (candidate.first_notified_at is None and item.status == 'POSTED'
                and not item.hidden and item.deleted_at is None and report.status == 'OPEN'
                and report.expires_at > now):
            await create_notification(
                db, event_id=candidate.id, recipient_id=report.owner_id,
                kind='MATCH_CANDIDATE', item_id=item.id, report_id=report.id, now=now,
            )
            candidate.first_notified_at = now

    async def finish(self, db, job, now, *, complete):
        result = await db.execute(update(MatchEvaluationJob).where(*self.fence(job)).values(
            completed_generation=job.claimed_generation if complete else MatchEvaluationJob.completed_generation,
            claimed_generation=None, lease_token=None, lease_until=None, attempts=0,
            next_attempt_at=now if complete else now + timedelta(seconds=5),
            updated_at=now, failed_at=None, last_error_code=None,
        ))
        if result.rowcount != 1:
            # Includes all candidate writes in this transaction.
            await db.rollback()

    async def process(self, job):
        pulse = asyncio.create_task(self.heartbeat(job))
        try:
            async with self.factory() as db, db.begin():
                await self.evaluate(db, job)
        except AnalysisError as error:
            await self.failure(job, error)
        except Exception:
            await self.failure(job, AnalysisError('MATCH_EVALUATION_FAILED', retryable=True))
        finally:
            pulse.cancel()
            with suppress(asyncio.CancelledError):
                await pulse

    async def failure(self, job, error):
        async with self.factory() as db, db.begin():
            current = (await db.execute(select(MatchEvaluationJob).where(*self.fence(job))
                .with_for_update())).scalar_one_or_none()
            if current is None:
                return
            current.attempts += 1
            retry = error.retryable and current.attempts < self.max_attempts
            now = self.clock()
            # A newer request must not be marked failed by an older generation.
            newer = current.requested_generation > job.claimed_generation
            current.failed_at = now if not retry and not newer else None
            current.last_error_code = error.code if current.failed_at else None
            current.next_attempt_at = now if newer else now + timedelta(
                seconds=random.uniform(0.5, 1) * min(300, 2 ** min(current.attempts, 9)),
            )
            if newer:
                current.attempts = 0
            current.claimed_generation = None
            current.lease_token = None
            current.lease_until = None
            current.updated_at = now

    async def run_once(self):
        job = await self.claim()
        if job is None:
            return False
        await self.process(job)
        return True

    async def run(self):
        while not self.stop.is_set():
            try:
                if await self.run_once():
                    continue
            except Exception:
                logger.error('MATCHING_WORKER_CYCLE_FAILED')
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self.stop.wait(), self.poll_seconds)

    def start(self):
        self.task = asyncio.create_task(self.run())

    async def close(self):
        self.stop.set()
        if self.task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self.task), 10)
            except asyncio.TimeoutError:
                self.task.cancel()
                with suppress(asyncio.CancelledError):
                    await self.task
