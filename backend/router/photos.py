"""Private photo uploads and expiring, reauthorized proxy access."""

from uuid import UUID

from fastapi import APIRouter, Request, Response

from library.photo_http import PhotoRoute
from schema.common import ErrorResponse
from schema.photos import PhotoAccessResponse, PhotoUploadResponse
from service.photos import service


router = APIRouter(tags=['photos'], route_class=PhotoRoute)

errors = {
    code: {'model': ErrorResponse}
    for code in (400, 401, 403, 404, 409, 410, 413, 415, 422, 503)
}
session_param = {
    'name': 'KAIFIND_SESSION',
    'in': 'cookie',
    'schema': {'type': 'string'},
}
csrf_param = {
    'name': 'X-CSRF-Token',
    'in': 'header',
    'required': True,
    'schema': {'type': 'string'},
}


@router.post(
    '/photos',
    summary='사진 업로드',
    status_code=201,
    response_model=PhotoUploadResponse,
    responses=errors,
    openapi_extra={
        'parameters': [dict(session_param, required=True), csrf_param],
        'requestBody': {
            'required': True,
            'content': {
                'multipart/form-data': {
                    'schema': {
                        'type': 'object',
                        'required': ['file', 'purpose'],
                        'additionalProperties': False,
                        'properties': {
                            'file': {'type': 'string', 'format': 'binary'},
                            'purpose': {
                                'type': 'string',
                                'enum': ['ITEM', 'DROP_OFF'],
                            },
                        },
                    },
                },
            },
        },
    },
)
async def upload_photo(request: Request):
    return await service(request).upload(request)


@router.post(
    '/photos/{photoId}/access-url',
    summary='사진 단기 링크',
    response_model=PhotoAccessResponse,
    responses=errors,
    openapi_extra={
        'parameters': [dict(session_param, required=True), csrf_param],
    },
)
async def create_photo_access_url(request: Request, photoId: UUID):
    return await service(request).issue_url(request, photoId)


@router.get(
    '/photo-access/{accessToken}',
    summary='사진 바이트',
    response_class=Response,
    responses={
        **errors,
        405: {'model': ErrorResponse},
        200: {
            'content': {
                mime: {'schema': {'type': 'string', 'format': 'binary'}}
                for mime in ('image/jpeg', 'image/png', 'image/webp')
            },
        },
    },
    openapi_extra={'parameters': [session_param]},
)
async def get_photo_content(request: Request, accessToken: str):
    content, mime = await service(request).content(request, accessToken)

    return Response(content, media_type=mime)


@router.head('/photo-access/{accessToken}', include_in_schema=False)
async def reject_photo_head(accessToken: str):
    # PhotoRoute rejects HEAD before this handler is called.
    raise AssertionError('HEAD guard missing')
