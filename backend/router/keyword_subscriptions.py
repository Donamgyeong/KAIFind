"""기능별 API 기본 구조. 상세 계약은 docs/api 참고."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, status

router = APIRouter(tags=["keyword_subscriptions"])


@router.get('/me/keyword-subscriptions', summary='list keyword subscriptions', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def list_keyword_subscriptions():
    """KEYWORD-01: list keyword subscriptions. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "KEYWORD-01 구현 예정"},
    )


@router.post('/me/keyword-subscriptions', summary='create keyword subscription', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def create_keyword_subscription():
    """KEYWORD-02: create keyword subscription. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "KEYWORD-02 구현 예정"},
    )


@router.delete('/me/keyword-subscriptions/{subscriptionId}', summary='delete keyword subscription', responses={501: {"description": "아직 구현되지 않은 기능"}})
async def delete_keyword_subscription(subscriptionId: UUID):
    """KEYWORD-03: delete keyword subscription. 요청·응답 모델과 서비스 연동 구현 예정."""
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail={"code": "NOT_IMPLEMENTED", "message": "KEYWORD-03 구현 예정"},
    )
