"""Auth transport guards and localized error responses, including validation errors."""
import logging

from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

from service.auth import AuthError, AuthService, clear_cookie, runtime

MESSAGES = {
    'KEYWORD_ALREADY_SUBSCRIBED': ('이미 구독한 키워드입니다.', 'This keyword is already subscribed.'),
    'KEYWORD_SUBSCRIPTION_NOT_FOUND': ('키워드 구독을 찾을 수 없습니다.', 'Keyword subscription not found.'),
    'KEYWORD_ANALYSIS_UNAVAILABLE': ('키워드 분석을 사용할 수 없습니다. 잠시 후 다시 시도해주세요.', 'Keyword analysis is unavailable. Please retry shortly.'),
    'NO_MATCHABLE_TERMS': ('비교할 수 있는 단어를 입력해주세요.', 'Enter at least one matchable word.'),
    'AUTH_REQUIRED': ('로그인이 필요합니다.', 'Please sign in.'),
    'SESSION_EXPIRED': ('세션이 만료되었습니다.', 'Your session has expired.'),
    'CSRF_INVALID': ('유효하지 않은 CSRF 토큰입니다.', 'Invalid CSRF token.'),
    'ORIGIN_NOT_ALLOWED': ('허용되지 않은 요청 출처입니다.', 'Request origin is not allowed.'),
    'INVALID_MOCK_ACCOUNT': ('사용할 수 없는 테스트 계정입니다.', 'The mock account is unavailable.'),
    'MOCK_AUTH_DISABLED': ('목업 인증이 비활성화되어 있습니다.', 'Mock authentication is disabled.'),
    'VALIDATION_ERROR': ('입력값을 확인해주세요.', 'Please check your input.'),
    'MALFORMED_JSON': ('올바른 JSON을 보내주세요.', 'Please provide valid JSON.'),
    'UNSUPPORTED_MEDIA_TYPE': ('application/json 형식이 필요합니다.', 'Content-Type must be application/json.'),
    'RATE_LIMITED': ('잠시 후 다시 시도해주세요.', 'Too many requests. Please try again later.'),
    'INTERNAL_SERVER_ERROR': ('서버 오류가 발생했습니다.', 'An internal server error occurred.'),
    'REQUIRED': ('필수 입력값입니다.', 'This field is required.'),
    'INVALID_TYPE': ('올바른 타입으로 입력해주세요.', 'Invalid value type.'),
    'INVALID_FORMAT': ('올바른 형식으로 입력해주세요.', 'Invalid value format.'),
    'UNKNOWN_FIELD': ('정의되지 않은 필드입니다.', 'Unknown field.'),
}


MESSAGES.update({
    'LOST_REPORT_NOT_OPEN': ('진행 중인 분실 신고가 아닙니다.', 'The lost report is not open.'),
    'COLLECTION_RESTRICTED': ('수거 권한이 제한되어 있습니다.', 'Collection permission is restricted.'),
    'COLLECTION_NOT_FOUND': ('현재 수거 기록을 찾을 수 없습니다.', 'Current collection not found.'),
    'ALREADY_COLLECTED': ('이미 수거된 물품입니다.', 'The item is already collected.'),
    'ITEM_NOT_POSTED': ('게시 중인 물품만 수거할 수 있습니다.', 'Only posted items can be collected.'),
    'NOTIFICATION_NOT_FOUND': ('알림을 찾을 수 없습니다.', 'Notification not found.'),
    'LOST_REPORT_NOT_FOUND': ('분실 신고를 찾을 수 없습니다.', 'Lost report not found.'),
    'MATCHING_PENDING': ('물품 비교가 진행 중입니다. 잠시 후 다시 시도해주세요.',
                         'Item matching is in progress. Please try again shortly.'),
    'ITEM_CLOSED': ('종료된 물품입니다.', 'The item is closed.'),
    'SELF_CONVERSATION': ('본인 물품에는 대화를 시작할 수 없습니다.', 'You cannot start a conversation about your own item.'),
    'CONVERSATION_NOT_FOUND': ('대화를 찾을 수 없습니다.', 'Conversation not found.'),
    'PHOTO_TOO_LARGE': ('사진 크기 제한을 초과했습니다.', 'Photo exceeds the size limit.'),
    'PHOTO_ALREADY_ATTACHED': ('이미 연결된 사진입니다.', 'Photo is already attached.'),
    'INVALID_REFERENCE': ('유효하지 않은 참조입니다.', 'Invalid reference.'),
    'INVALID_IMAGE': ('지원되는 올바른 사진을 보내주세요.', 'Provide a valid JPEG, PNG or WebP image.'),
    'PHOTO_FORBIDDEN': ('사진에 접근할 권한이 없습니다.', 'You cannot access this photo.'),
    'PHOTO_LINK_EXPIRED': ('사진 링크가 만료되었습니다.', 'The photo link has expired.'),
    'PHOTO_MULTIPART_REQUIRED': ('multipart/form-data 형식이 필요합니다.', 'Content-Type must be multipart/form-data.'),
    'PHOTO_STORAGE_UNAVAILABLE': ('사진 저장소를 사용할 수 없습니다.', 'Photo storage is unavailable.'),
    'PHOTO_METHOD_NOT_ALLOWED': ('지원하지 않는 사진 요청입니다.', 'This photo request is not supported.'),
    'FORBIDDEN': ('접근 권한이 없습니다.', 'You do not have permission to access this resource.'),
    'FINDER_ONLY': ('게시물 작성자만 이의를 제기할 수 있습니다.', 'Only the item finder can submit a dispute.'),
    'ITEM_NOT_COLLECTED': ('현재 유효한 수거 기록이 없습니다.', 'The item has no current collection.'),
    'OPEN_DISPUTE_EXISTS': ('검토 대기 중인 분쟁이 있습니다.', 'An open dispute already exists.'),
    'NOT_FOUND': ('대상을 찾을 수 없습니다.', 'Resource not found.'),
    'LAST_ADMIN': ('마지막 관리자 권한은 회수할 수 없습니다.', 'The last administrator cannot be removed.'),
    'BUILDING_CODE_EXISTS': ('이미 사용 중인 건물 코드입니다.', 'Building code already exists.'),
    'CATEGORY_NAME_EXISTS': ('이미 사용 중인 카테고리 이름입니다.', 'Category name already exists.'),
    'OPEN_REPORT_EXISTS': ('검토 대기 중인 신고가 있습니다.', 'An open report already exists.'),
    'REPORT_ALREADY_REVIEWED': ('이미 검토된 신고입니다.', 'Report has already been reviewed.'),
    'DISPUTE_ALREADY_RESOLVED': ('이미 처리된 분쟁입니다.', 'Dispute has already been resolved.'),
    'INVALID_DECISION': ('기각 시 수거자를 제한할 수 없습니다.', 'A dismissed dispute cannot restrict the collector.'),
    'DISPUTE_NOT_UPHELD': ('인용 완료된 분쟁이 필요합니다.', 'A resolved, upheld dispute is required.'),
    'COLLECTOR_MISMATCH': ('분쟁의 수거자와 대상 회원이 다릅니다.', 'The user is not the disputed collector.'),
    'INVALID_TIME_RANGE': ('종료 시각은 시작 시각 이후여야 합니다.', 'End time must be after start time.'),
    'CONCURRENT_MODIFICATION': ('동시 변경이 발생했습니다. 다시 시도해주세요.', 'Concurrent modification; please retry.'),
})


def language(request):
    return 'en' if request.headers.get('accept-language') == 'en' else 'ko'


def message(code, lang):
    return MESSAGES[code][lang == 'en']


def error_response(error, request):
    lang = language(request)
    fields = [dict(field=e['field'], code=e['code'], message=message(e['code'], lang)) for e in error.fields]
    response = JSONResponse(status_code=error.status, headers=error.headers,
        content=dict(code=error.code, message=message(error.code, lang), fieldErrors=fields))
    if error.clear_cookie:
        clear_cookie(response)
    return response


def validation_error(exc):
    fields = []
    for error in exc.errors():
        kind = error['type']
        if kind == 'json_invalid':
            return AuthError(400, 'MALFORMED_JSON')
        if kind == 'missing':
            code = 'REQUIRED'
        elif kind == 'extra_forbidden':
            code = 'UNKNOWN_FIELD'
        elif kind.endswith('_type') or kind.endswith('_parsing'):
            code = 'INVALID_TYPE'
        else:
            code = 'INVALID_FORMAT'
        fields.append(dict(field='.'.join(map(str, error['loc'][1:])) or 'body', code=code))
    return AuthError(400, 'VALIDATION_ERROR', fields=fields)


class AuthRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()
        async def handle(request):
            try:
                rt = runtime(request)
                path = request.url.path
                if path.endswith(('/mock/accounts', '/mock/login')) and not rt.settings.allow_mock:
                    raise AuthError(404, 'MOCK_AUTH_DISABLED')
                if request.method == 'POST':
                    origin = request.headers.get('origin')
                    if origin is not None and origin not in rt.settings.allowed_origins:
                        raise AuthError(403, 'ORIGIN_NOT_ALLOWED')
                    if path.endswith('/mock/login'):
                        # Trust the socket peer, never unverified forwarded headers.
                        await AuthService(rt).rate_limit(request.client.host if request.client else 'unknown')
                        media_type = request.headers.get('content-type', '').split(';')[0].strip().lower()
                        if media_type != 'application/json':
                            raise AuthError(415, 'UNSUPPORTED_MEDIA_TYPE')
                        try:
                            await request.json()
                        except (ValueError, UnicodeError):
                            raise AuthError(400, 'MALFORMED_JSON')
                    if not request.cookies.get('KAIFIND_SESSION') or not request.headers.get('x-csrf-token'):
                        raise AuthError(403, 'CSRF_INVALID')
                elif path.endswith('/me') and not request.cookies.get('KAIFIND_SESSION'):
                    raise AuthError(401, 'AUTH_REQUIRED')
                try:
                    response = await handler(request)
                except RequestValidationError as exc:
                    raise validation_error(exc) from None
            except AuthError as exc:
                response = error_response(exc, request)
            except Exception:
                # Do not log request bodies, cookies, tokens or DB exception details.
                logging.getLogger(__name__).error('Auth request failed')
                response = error_response(AuthError(500, 'INTERNAL_SERVER_ERROR'), request)
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Content-Language'] = language(request)
            return response
        return handle
