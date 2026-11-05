"""Public read routes share error handling without session authentication."""

import logging

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from library.auth_http import error_response, language, validation_error
from library.database import session_factory
from service.auth import AuthError


class ReferenceRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                factory = getattr(request.app.state, 'reference_session_factory', None)
                if factory is None:
                    factory = session_factory()

                async with factory() as db, db.begin():
                    request.state.db = db
                    response = await handler(request)
            except RequestValidationError as exc:
                response = error_response(validation_error(exc), request)
            except Exception:
                logging.getLogger(__name__).error('Reference request failed')
                response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)

            response.headers['Cache-Control'] = 'no-store'
            response.headers['Content-Language'] = language(request)
            return response

        return handle
