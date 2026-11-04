"""Photo error contract and access-token log redaction."""

import logging
import re

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from minio.error import S3Error
from sqlalchemy.exc import DBAPIError
from urllib3.exceptions import HTTPError

from library.auth_http import error_response, language, validation_error
from service.auth import AuthError


class PhotoAccessLogFilter(logging.Filter):
    def filter(self, record):
        def redact(value):
            return (
                re.sub(r'(/api/v1/photo-access/)[^\s?"\']+', r'\1[redacted]', value)
                if isinstance(value, str)
                else value
            )

        record.msg = redact(record.msg)

        # Preserve Uvicorn's five arguments: its AccessFormatter unpacks them.
        if isinstance(record.args, tuple):
            record.args = tuple(redact(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {key: redact(value) for key, value in record.args.items()}

        return True


def install_photo_log_filter():
    logger = logging.getLogger('uvicorn.access')
    if not any(isinstance(f, PhotoAccessLogFilter) for f in logger.filters):
        logger.addFilter(PhotoAccessLogFilter())


class PhotoRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                if request.method == 'HEAD' or (request.method == 'GET' and 'range' in request.headers):
                    raise AuthError(405, 'PHOTO_METHOD_NOT_ALLOWED', headers={'Allow': 'GET'})

                try:
                    response = await handler(request)
                except RequestValidationError as exc:
                    raise validation_error(exc) from None
            except AuthError as exc:
                response = error_response(exc, request)
            except (S3Error, HTTPError, ConnectionError, TimeoutError):
                response = error_response(AuthError(503, 'PHOTO_STORAGE_UNAVAILABLE'), request)
            except DBAPIError as exc:
                state = getattr(exc.orig, 'sqlstate', None)
                code = 'CONCURRENT_MODIFICATION' if state in {'40P01', '40001'} else 'INTERNAL_SERVER_ERROR'
                response = error_response(AuthError(409 if code == 'CONCURRENT_MODIFICATION' else 500, code), request)
            except Exception:
                logging.getLogger(__name__).error('Photo request failed')
                response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)

            response.headers.update({
                'Cache-Control': 'private, no-store',
                'Content-Language': language(request),
                'Referrer-Policy': 'no-referrer',
                'X-Content-Type-Options': 'nosniff',
            })

            return response

        return handle
