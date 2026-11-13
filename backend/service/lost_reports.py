"""Lost report operations within the authenticated request transaction."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, inspect, select
from sqlalchemy.orm.attributes import flag_modified

from library.matching_lock import lock_matching_categories
from model import Building, Category, LostReport, LostReportBuilding, LostReportPrivateDetail
from schema.lost_reports import LostReportPage, LostReportResponse, LostReportSummary
from service.audit import append_audit, one_year_after
from service.auth import AuthError
from service.matching import matching_progress
from service.text_analysis import request_lost_report_analysis, request_report_reevaluation


class LostReportService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user
        self.now = request.state.now

    async def buildings(self, report):
        return list((await self.db.scalars(select(LostReportBuilding.building_id).where(
            LostReportBuilding.report_id == report.id,
        ).order_by(LostReportBuilding.building_id))).all())

    async def references(self, body, report=None):
        if body.lost_date_to > self.now.astimezone(ZoneInfo('Asia/Seoul')).date():
            raise AuthError(400, 'VALIDATION_ERROR', fields=[
                {'field': 'lostDateTo', 'code': 'INVALID_FORMAT'},
            ])
        old_buildings = set(await self.buildings(report)) if report else set()
        category = await self.db.get(Category, body.category_id)
        if category is None or (not category.active and (
            report is None or report.category_id != body.category_id
        )):
            raise AuthError(400, 'INVALID_REFERENCE')
        selected = set(body.possible_building_ids)
        rows = (await self.db.scalars(select(Building).where(Building.id.in_(selected)))).all()
        if len(rows) != len(selected) or any(not row.active and row.id not in old_buildings for row in rows):
            raise AuthError(400, 'INVALID_REFERENCE')

    async def load(self, report_id, *, writing=False, extra_categories=()):
        report = await self.db.scalar(select(LostReport).where(LostReport.id == report_id))
        if report is None or (report.owner_id != self.user.id and (writing or self.user.role != 'ADMIN')):
            raise AuthError(404, 'LOST_REPORT_NOT_FOUND')
        category = report.category_id
        await lock_matching_categories(self.db, [category, *extra_categories])
        report = await self.db.scalar(select(LostReport).where(
            LostReport.id == report_id,
        ).with_for_update().execution_options(populate_existing=True))
        if report is None:
            raise AuthError(404, 'LOST_REPORT_NOT_FOUND')
        if report.category_id != category:
            raise AuthError(409, 'CONCURRENT_MODIFICATION')
        if report.status == 'OPEN' and report.expires_at <= self.now:
            await self.close(report, 'CLOSED', actor=None)
        return report

    async def close(self, report, status, *, actor):
        previous = report.status
        report.status = status
        report.updated_at = self.now
        flag_modified(report, 'updated_at')
        if report.closed_at is None:
            report.closed_at = self.now
            report.purge_after = one_year_after(self.now)
        await self.db.flush()
        # The DB cleanup trigger deletes private details and cancels queued emails.
        append_audit(self.db, actor, 'LOST_REPORT_STATUS_CHANGED', 'LOST_REPORT', report.id,
                     self.now, fromStatus=previous, toStatus=status)
        await self.db.flush()

    async def response(self, report, *, summary=False, buildings=None):
        await self.db.flush()
        if inspect(report).expired_attributes:
            await self.db.refresh(report)
        progress = await matching_progress(self.db, report=report, now=self.now)
        data = dict(
            reportId=report.id, ownerId=report.owner_id, categoryId=report.category_id,
            description=report.description,
            possibleBuildingIds=await self.buildings(report) if buildings is None else buildings,
            lostDateFrom=report.lost_date_from, lostDateTo=report.lost_date_to,
            status=report.status, createdAt=report.created_at, updatedAt=report.updated_at,
            expiresAt=report.expires_at, closedAt=report.closed_at,
            **progress.model_dump(by_alias=True),
        )
        if summary:
            return LostReportSummary(**data)
        details = await self.db.get(LostReportPrivateDetail, report.id)
        return LostReportResponse(**data, privateIdentifyingDetails=(
            details.details if details and report.status == 'OPEN' else None
        ))

    async def replace_fields(self, report, body):
        report.category_id = body.category_id
        report.description = body.description
        report.lost_date_from = body.lost_date_from
        report.lost_date_to = body.lost_date_to
        report.updated_at = self.now
        flag_modified(report, 'updated_at')
        await self.db.execute(delete(LostReportBuilding).where(LostReportBuilding.report_id == report.id))
        self.db.add_all([
            LostReportBuilding(report_id=report.id, building_id=value)
            for value in body.possible_building_ids
        ])
        details = await self.db.get(LostReportPrivateDetail, report.id)
        if details is None:
            self.db.add(LostReportPrivateDetail(report_id=report.id, details=body.private_identifying_details))
        else:
            details.details = body.private_identifying_details
        await self.db.flush()

    async def create(self, body):
        await lock_matching_categories(self.db, [body.category_id])
        await self.references(body)
        report = LostReport(
            owner_id=self.user.id, category_id=body.category_id, description=body.description,
            lost_date_from=body.lost_date_from, lost_date_to=body.lost_date_to,
            status='OPEN', created_at=self.now, updated_at=self.now,
            expires_at=self.now + timedelta(days=30),
        )
        self.db.add(report)
        await self.db.flush()
        await self.replace_fields(report, body)
        await request_lost_report_analysis(self.db, report=report, now=self.now)
        append_audit(self.db, self.user, 'LOST_REPORT_STATUS_CHANGED', 'LOST_REPORT', report.id,
                     self.now, toStatus='OPEN')
        return await self.response(report)

    async def update(self, report_id, body):
        report = await self.load(report_id, writing=True, extra_categories=[body.category_id])
        if report.status != 'OPEN':
            return None
        await self.references(body, report)
        changed_text = report.description != body.description
        # Even a private-only replacement invalidates versioned candidate evidence.
        report.version += 1
        await self.replace_fields(report, body)
        if changed_text:
            await request_lost_report_analysis(self.db, report=report, now=self.now)
        else:
            await request_report_reevaluation(self.db, report=report, now=self.now)
        return await self.response(report)

    async def extend(self, report_id):
        report = await self.load(report_id, writing=True)
        if report.status != 'OPEN':
            return None
        report.expires_at = max(report.expires_at, self.now) + timedelta(days=30)
        report.updated_at = self.now
        flag_modified(report, 'updated_at')
        await self.db.flush()
        await request_report_reevaluation(self.db, report=report, now=self.now)
        return await self.response(report)

    async def resolve(self, report_id):
        report = await self.load(report_id, writing=True)
        if report.status != 'RESOLVED':
            await self.close(report, 'RESOLVED', actor=self.user)
        return await self.response(report)

    async def list(self, params):
        # Normalize expired rows before filtering, in deterministic category order.
        expired = (await self.db.execute(select(LostReport.id, LostReport.category_id).where(
            LostReport.owner_id == self.user.id, LostReport.status == 'OPEN',
            LostReport.expires_at <= self.now,
        ))).all()
        if expired:
            await lock_matching_categories(self.db, [row.category_id for row in expired])
            for row in sorted(expired, key=lambda value: value.id):
                report = await self.db.scalar(select(LostReport).where(
                    LostReport.id == row.id,
                ).with_for_update().execution_options(populate_existing=True))
                if report is not None:
                    if report.category_id != row.category_id:
                        raise AuthError(409, 'CONCURRENT_MODIFICATION')
                    if report.status == 'OPEN' and report.expires_at <= self.now:
                        await self.close(report, 'CLOSED', actor=None)
        filters = [LostReport.owner_id == self.user.id]
        if params.status is not None:
            filters.append(LostReport.status == params.status)
        total = await self.db.scalar(select(func.count()).select_from(LostReport).where(*filters))
        reports = (await self.db.scalars(select(LostReport).where(*filters).order_by(
            LostReport.created_at.desc(), LostReport.id.desc(),
        ).offset(params.page * params.size).limit(params.size))).all()
        buildings = {report.id: [] for report in reports}
        if reports:
            connections = (await self.db.execute(select(LostReportBuilding).where(
                LostReportBuilding.report_id.in_(buildings),
            ).order_by(LostReportBuilding.building_id))).scalars()
            for connection in connections:
                buildings[connection.report_id].append(connection.building_id)
        return LostReportPage(
            items=[await self.response(report, summary=True, buildings=buildings[report.id])
                   for report in reports],
            page=params.page, size=params.size, totalElements=total,
            totalPages=(total + params.size - 1) // params.size,
        )
