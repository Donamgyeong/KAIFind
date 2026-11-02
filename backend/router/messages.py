"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["messages"])


@router.post('/conversations', summary='물품별 대화 시작·재사용', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_conversation():
    """MSG-01: 물품별 대화 시작·재사용. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MSG-01 구현 예정"},
    )


@router.get('/conversations', summary='내 대화 목록', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_conversations():
    """MSG-02: 내 대화 목록. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MSG-02 구현 예정"},
    )


@router.get('/conversations/{conversationId}/messages', summary='메시지 조회', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_messages(conversationId: UUID):
    """MSG-03: 메시지 조회. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MSG-03 구현 예정"},
    )


@router.post('/conversations/{conversationId}/messages', summary='메시지 전송', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def send_message(conversationId: UUID):
    """MSG-04: 메시지 전송. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "MSG-04 구현 예정"},
    )
