"""API v1 라우터 등록."""

from fastapi import APIRouter

from router import (
    admin,
    auth,
    collections,
    disputes,
    found_items,
    keyword_subscriptions,
    lost_reports,
    matching,
    messages,
    notifications,
    photos,
    profile,
    reference,
)

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(admin.router)
api_router.include_router(auth.router)
api_router.include_router(collections.router)
api_router.include_router(disputes.router)
api_router.include_router(found_items.router)
api_router.include_router(keyword_subscriptions.router)
api_router.include_router(lost_reports.router)
api_router.include_router(matching.router)
api_router.include_router(messages.router)
api_router.include_router(notifications.router)
api_router.include_router(photos.router)
api_router.include_router(profile.router)
api_router.include_router(reference.router)
