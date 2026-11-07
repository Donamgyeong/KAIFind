"""Participant-only messaging within the protected request transaction."""

from sqlalchemy import func, or_, select

from model import Conversation, FoundItem, Message
from schema.messages import ConversationResponse, MessagePage, MessageResponse
from service.auth import AuthError


class MessageService:
    def __init__(self, request):
        self.db = request.state.db
        self.user = request.state.user
        self.now = request.state.now

    @staticmethod
    def conversation_response(row, finder_id):
        return ConversationResponse(
            conversationId=row.id, itemId=row.item_id, finderId=finder_id,
            memberId=row.member_id, createdAt=row.created_at, updatedAt=row.updated_at,
        )

    @staticmethod
    def message_response(row):
        return MessageResponse(
            messageId=row.id, conversationId=row.conversation_id,
            senderId=row.sender_id, content=row.content, createdAt=row.created_at,
        )

    async def create(self, item_id):
        item = await self.db.scalar(
            select(FoundItem).where(FoundItem.id == item_id).with_for_update(),
        )
        if item is None or item.deleted_at is not None or item.hidden:
            raise AuthError(404, 'NOT_FOUND')
        if item.status != 'POSTED':
            raise AuthError(409, 'ITEM_CLOSED')
        if item.finder_id == self.user.id:
            raise AuthError(409, 'SELF_CONVERSATION')

        row = await self.db.scalar(select(Conversation).where(
            Conversation.item_id == item.id, Conversation.member_id == self.user.id,
        ))
        created = row is None
        if created:
            row = Conversation(
                item_id=item.id, member_id=self.user.id,
                created_at=self.now, updated_at=self.now,
            )
            self.db.add(row)
            await self.db.flush()

        return self.conversation_response(row, item.finder_id), created

    async def page(self, query, params, convert):
        total = await self.db.scalar(select(func.count()).select_from(query.subquery()))
        rows = await self.db.execute(query.offset(params.page * params.size).limit(params.size))
        return MessagePage(
            items=[convert(row) for row in rows], page=params.page, size=params.size,
            totalElements=total, totalPages=(total + params.size - 1) // params.size,
        )

    async def conversations(self, params):
        query = select(Conversation, FoundItem.finder_id).join(FoundItem).where(
            or_(Conversation.member_id == self.user.id, FoundItem.finder_id == self.user.id),
            FoundItem.status == 'POSTED', FoundItem.deleted_at.is_(None),
        )
        if params.item_id is not None:
            query = query.where(Conversation.item_id == params.item_id)
        query = query.order_by(Conversation.updated_at.desc(), Conversation.id.desc())
        return await self.page(query, params, lambda row: self.conversation_response(*row))

    async def participant(self, conversation_id, *, writing=False):
        query = select(Conversation, FoundItem).join(FoundItem).where(
            Conversation.id == conversation_id,
            or_(Conversation.member_id == self.user.id, FoundItem.finder_id == self.user.id),
        )
        if writing:
            # Lock the item first; closure deletes conversations while holding this lock.
            item_id = await self.db.scalar(query.with_only_columns(FoundItem.id))
            if item_id is None:
                raise AuthError(404, 'CONVERSATION_NOT_FOUND')
            await self.db.execute(select(FoundItem.id).where(
                FoundItem.id == item_id,
            ).with_for_update())

        row = (await self.db.execute(query)).first()
        if row is None:
            raise AuthError(404, 'CONVERSATION_NOT_FOUND')
        conversation, item = row
        if item.status != 'POSTED' or item.deleted_at is not None:
            raise AuthError(409 if writing else 404,
                            'ITEM_CLOSED' if writing else 'CONVERSATION_NOT_FOUND')
        return conversation

    async def messages(self, conversation_id, params):
        await self.participant(conversation_id)
        query = select(Message).where(Message.conversation_id == conversation_id).order_by(
            Message.created_at, Message.id,
        )
        return await self.page(query, params, lambda row: self.message_response(row[0]))

    async def send(self, conversation_id, content):
        conversation = await self.participant(conversation_id, writing=True)
        row = Message(
            conversation_id=conversation.id, sender_id=self.user.id,
            content=content, created_at=self.now,
        )
        self.db.add(row)
        conversation.updated_at = self.now
        await self.db.flush()

        return self.message_response(row)
