"""Public routes that serve guests and still recognise a signed-in member.

ProtectedRoute answers 401 without a session; ReferenceRoute ignores sessions. Item
reads need the middle ground: request.state.user is None for guests and the member
when a live session exists, so one handler can narrow what each audience sees.
"""

import logging

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError

from library.auth_http import error_response, language, validation_error
from library.protected_http import ROLE_LOCK
from model import User
from service.auth import COOKIE, IDLE, AuthError, AuthService, runtime


class OptionalAuthRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        extra = dict(kwargs.get('openapi_extra') or {})
        parameters = list(extra.get('parameters', []))
        common = [
            {'name': 'KAIFIND_SESSION', 'in': 'cookie', 'required': False,
             'schema': {'type': 'string'}},
            {'name': 'Accept-Language', 'in': 'header', 'required': False,
             'schema': {'type': 'string', 'enum': ['ko', 'en'], 'default': 'ko'}},
        ]
        existing = {(p['name'], p['in']) for p in parameters}
        parameters.extend(p for p in common if (p['name'], p['in']) not in existing)
        extra['parameters'] = parameters
        kwargs['openapi_extra'] = extra
        super().__init__(*args, **kwargs)

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def handle(request):
            try:
                rt = runtime(request)
                async with rt.factory() as db, db.begin():
                    # Shared with every protected request so a role change cannot race a read.
                    await db.execute(text('SELECT pg_advisory_xact_lock_shared(:key)'), {'key': ROLE_LOCK})
                    auth = AuthService(rt)
                    session = await auth.lookup(db, request.cookies.get(COOKIE))
                    now = rt.clock()

                    # Missing, expired and anonymous sessions are all plain guests here.
                    user = None
                    if session is not None and session.user_id is not None and not auth.expired(session, now):
                        user = await db.scalar(select(User).where(User.id == session.user_id))
                        if user is not None:
                            session.last_activity_at = now
                            session.idle_expires_at = min(now + IDLE, session.absolute_expires_at)

                    request.state.db, request.state.user, request.state.now = db, user, now
                    try:
                        response = await handler(request)
                    except RequestValidationError as exc:
                        raise validation_error(exc) from None
            except AuthError as exc:
                response = error_response(exc, request)
            except DBAPIError as exc:
                state = getattr(exc.orig, 'sqlstate', None)
                if state in {'40P01', '40001', '55P03'}:
                    response = error_response(AuthError(409, 'CONCURRENT_MODIFICATION'), request)
                else:
                    logging.getLogger(__name__).error('Optional-auth request database failure')
                    response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)
            except Exception:
                logging.getLogger(__name__).error('Optional-auth request failed')
                response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)

            # The body depends on who is asking, so no shared cache may keep it.
            response.headers['Cache-Control'] = 'private, no-store'
            response.headers['Content-Language'] = language(request)
            return response

        return handle
