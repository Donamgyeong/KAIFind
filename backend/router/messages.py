"""Authenticated item conversations and messages."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response

from library.protected_http import ProtectedRoute
from schema.common import ErrorResponse
from schema.message_params import ConversationParams, MessageParams
from schema.messages import (
    ConversationResponse, CreateConversationRequest, MessagePage,
    MessageResponse, SendMessageRequest,
)
from service.messages import MessageService


router = APIRouter(
    tags=['messages'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 404, 409, 415, 500)},
)


@router.post(
    '/conversations', summary='물품별 대화 시작·재사용', status_code=201,
    response_model=ConversationResponse, responses={200: {'model': ConversationResponse}},
)
async def create_conversation(request: Request, response: Response, body: CreateConversationRequest):
    result, created = await MessageService(request).create(body.item_id)
    response.status_code = 201 if created else 200
    return result


@router.get('/conversations', summary='내 대화 목록', response_model=MessagePage[ConversationResponse])
async def list_conversations(request: Request, params: Annotated[ConversationParams, Query()]):
    return await MessageService(request).conversations(params)


@router.get(
    '/conversations/{conversationId}/messages', summary='메시지 조회',
    response_model=MessagePage[MessageResponse],
)
async def list_messages(
    request: Request, conversationId: UUID, params: Annotated[MessageParams, Query()],
):
    return await MessageService(request).messages(conversationId, params)


@router.post(
    '/conversations/{conversationId}/messages', summary='메시지 전송',
    status_code=201, response_model=MessageResponse,
)
async def send_message(request: Request, conversationId: UUID, body: SendMessageRequest):
    return await MessageService(request).send(conversationId, body.content)
