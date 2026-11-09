"""Authenticated routes own one transaction spanning authorization and mutation."""
import logging

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, DBAPIError

from library.auth_http import error_response, language, validation_error
from model import User
from service.auth import AuthError, AuthService, IDLE, runtime

# Shared by every protected request; role changes take the exclusive counterpart.
# Acquire before session/user locks so revocation cannot race an authorized action.
ROLE_LOCK = 73011801
CONFLICTS = {
    'uq_collections_active_item': 'ALREADY_COLLECTED',
    'uq_buildings_code_normalized': 'BUILDING_CODE_EXISTS',
    'uq_buildings_code': 'BUILDING_CODE_EXISTS',
    'uq_categories_name_ko_normalized': 'CATEGORY_NAME_EXISTS',
    'uq_categories_name_en_normalized': 'CATEGORY_NAME_EXISTS',
    'uq_post_reports_open_reporter': 'OPEN_REPORT_EXISTS',
    'uq_disputes_open_collection': 'OPEN_DISPUTE_EXISTS',
}


def constraint_name(exc):
    original = exc.orig
    diag = getattr(original, 'diag', None)
    return (getattr(diag, 'constraint_name', None)
            or getattr(original, 'constraint_name', None)
            or getattr(getattr(original, '__cause__', None), 'constraint_name', None))


class ProtectedRoute(APIRoute):
    def __init__(self, *args, **kwargs):
        extra = dict(kwargs.get('openapi_extra') or {})
        parameters = list(extra.get('parameters', []))
        common = [
            {'name': 'KAIFIND_SESSION', 'in': 'cookie', 'required': True,
             'schema': {'type': 'string'}},
            {'name': 'Accept-Language', 'in': 'header', 'required': False,
             'schema': {'type': 'string', 'enum': ['ko', 'en'], 'default': 'ko'}},
        ]
        if set(kwargs.get('methods') or []) & {'POST', 'PATCH', 'PUT', 'DELETE'}:
            common.append({'name': 'X-CSRF-Token', 'in': 'header', 'required': True,
                           'schema': {'type': 'string'}})
            common.append({'name': 'Origin', 'in': 'header', 'required': False,
                           'description': '제공된 경우 서버 허용 목록 검사', 'schema': {'type': 'string'}})
        existing = {(p['name'], p['in']) for p in parameters}
        parameters.extend(p for p in common if (p['name'], p['in']) not in existing)
        extra['parameters'] = parameters
        kwargs['openapi_extra'] = extra
        super().__init__(*args, **kwargs)

        # Only routes with a declared body require its media-type header.
        if self.body_field is not None and ('Content-Type', 'header') not in existing:
            parameters.append({
                'name': 'Content-Type', 'in': 'header', 'required': True,
                'schema': {'type': 'string', 'enum': ['application/json']},
            })

    def get_route_handler(self):
        handler = super().get_route_handler()
        has_body_model = self.body_field is not None

        async def handle(request):
            try:
                rt = runtime(request)
                writing = request.method in {'POST', 'PATCH', 'PUT', 'DELETE'}
                async with rt.factory() as db, db.begin():
                    role_change = request.method == 'PATCH' and request.url.path.endswith('/role')
                    lock = 'pg_advisory_xact_lock' if role_change else 'pg_advisory_xact_lock_shared'
                    await db.execute(text(f'SELECT {lock}(:key)'), {'key': ROLE_LOCK})
                    auth = AuthService(rt)
                    session = await auth.lookup(db, request.cookies.get('KAIFIND_SESSION'))
                    now = rt.clock()
                    error = None
                    if session is None:
                        error = AuthError(401, 'AUTH_REQUIRED')
                    elif auth.expired(session, now):
                        await db.delete(session)
                        error = AuthError(401, 'SESSION_EXPIRED', clear_cookie=True)
                    elif session.user_id is None:
                        error = AuthError(401, 'AUTH_REQUIRED')
                    if error:
                        response = error_response(error, request)
                    else:
                        user = await db.scalar(select(User).where(User.id == session.user_id))
                        if user is None:
                            raise AuthError(401, 'AUTH_REQUIRED', clear_cookie=True)
                        if '/admin/' in request.url.path and user.role != 'ADMIN':
                            raise AuthError(403, 'FORBIDDEN')
                        if writing:
                            origin = request.headers.get('origin')
                            if origin is not None and origin not in rt.settings.allowed_origins:
                                raise AuthError(403, 'ORIGIN_NOT_ALLOWED')
                            auth.require_csrf(session, request.headers.get('x-csrf-token'), now)
                            if has_body_model:
                                media_type = request.headers.get('content-type', '').split(';')[0].strip().lower()
                                if media_type != 'application/json':
                                    raise AuthError(415, 'UNSUPPORTED_MEDIA_TYPE')
                                try:
                                    await request.json()
                                except (ValueError, UnicodeError):
                                    raise AuthError(400, 'MALFORMED_JSON') from None
                            elif await request.body():
                                raise AuthError(400, 'VALIDATION_ERROR')
                        session.last_activity_at = now
                        session.idle_expires_at = min(now + IDLE, session.absolute_expires_at)
                        request.state.db, request.state.user, request.state.now = db, user, now
                        try:
                            response = await handler(request)
                        except RequestValidationError as exc:
                            raise validation_error(exc) from None
            except AuthError as exc:
                response = error_response(exc, request)
            except IntegrityError as exc:
                code = CONFLICTS.get(constraint_name(exc))
                if code:
                    response = error_response(AuthError(409, code), request)
                else:
                    logging.getLogger(__name__).error('Protected request integrity failure')
                    response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)
            except DBAPIError as exc:
                state = getattr(exc.orig, 'sqlstate', None)
                if state in {'40P01', '40001', '55P03'}:
                    response = error_response(AuthError(409, 'CONCURRENT_MODIFICATION'), request)
                else:
                    logging.getLogger(__name__).error('Protected request database failure')
                    response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)
            except Exception:
                logging.getLogger(__name__).error('Protected request failed')
                response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Content-Language'] = language(request)
            return response
        return handle
