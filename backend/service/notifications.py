"""Owner-scoped notifications within the protected request transaction."""

from sqlalchemy import func, select, true, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import aliased

from library.auth_http import language
from model import Notification, NotificationSetting
from schema.notifications import (
    NotificationPage, NotificationResponse, NotificationSettingsResponse,
)
from service.auth import AuthError


MESSAGES = {
    'MATCH_CANDIDATE': (
        '분실 신고와 일치할 수 있는 습득물이 등록되었습니다.',
        'A found item may match your lost report.',
    ),
    'ITEM_COLLECTED': ('등록한 습득물의 수거가 완료되었습니다.', 'Your found item has been collected.'),
    'ITEM_EXPIRED': ('등록한 습득물의 보관 기간이 만료되었습니다.', 'Your found item has expired.'),
    'KEYWORD_MATCH': (
        '구독한 키워드와 일치하는 습득물이 등록되었습니다.',
        'A found item matches your subscribed keyword.',
    ),
}


class NotificationService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user
        self.now = request.state.now
        self.lang = language(request)

    @staticmethod
    def settings_response(row):
        return NotificationSettingsResponse(**{
            field.alias: getattr(row, name) if row is not None else True
            for name, field in NotificationSettingsResponse.model_fields.items()
        })

    async def settings(self):
        row = await self.db.get(NotificationSetting, self.user.id)
        return self.settings_response(row)

    async def replace_settings(self, body):
        values = body.model_dump(by_alias=False)
        statement = insert(NotificationSetting).values(user_id=self.user.id, **values)
        row = await self.db.scalar(statement.on_conflict_do_update(
            index_elements=[NotificationSetting.user_id],
            set_={**values, 'updated_at': self.now},
        ).returning(NotificationSetting))
        return self.settings_response(row)

    def response(self, row):
        path = (
            (f'/lost-reports/{row.report_id}/matches' if row.report_id else '/lost-reports')
            if row.type == 'MATCH_CANDIDATE'
            else (f'/found-items/{row.item_id}' if row.item_id else '/found-items')
        )
        return NotificationResponse(
            notificationId=row.id, type=row.type,
            message=MESSAGES[row.type][self.lang == 'en'], targetPath=path,
            itemId=row.item_id, reportId=row.report_id,
            createdAt=row.created_at, readAt=row.read_at,
        )

    def visible(self):
        return (
            Notification.recipient_id == self.user.id,
            Notification.purge_after > self.now,
        )

    async def list(self, params):
        query = select(Notification).where(*self.visible())
        if params.unread_only:
            query = query.where(Notification.read_at.is_(None))

        filtered = query.cte('filtered_notifications')
        total = select(func.count().label('total')).select_from(filtered).cte('notification_total')
        page = select(filtered).order_by(
            filtered.c.created_at.desc(), filtered.c.id.desc(),
        ).offset(params.page * params.size).limit(params.size).cte('notification_page')
        entity = aliased(Notification, page)
        rows = (await self.db.execute(
            select(total.c.total, entity).select_from(total.outerjoin(page, true()))
            .order_by(page.c.created_at.desc(), page.c.id.desc()),
        )).all()
        count = rows[0][0]
        return NotificationPage(
            items=[self.response(row) for _, row in rows if row is not None],
            page=params.page, size=params.size, totalElements=count,
            totalPages=(count + params.size - 1) // params.size,
        )

    async def mark_read(self, notification_id):
        row = await self.db.scalar(update(Notification).where(
            Notification.id == notification_id, *self.visible(),
        ).values(read_at=func.coalesce(Notification.read_at, self.now)).returning(Notification))
        if row is None:
            raise AuthError(404, 'NOTIFICATION_NOT_FOUND')
        return self.response(row)
