"""Authenticated keyword subscriptions with analysis before final persistence."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from library.keyword_subscription_matching import atomic_terms
from library.protected_http import ProtectedRoute
from library.text_analysis_types import AnalysisError, AnalysisInput
from schema.common import ErrorResponse
from schema.keyword_subscription_params import KeywordSubscriptionParams
from schema.keyword_subscriptions import (
    CreateKeywordSubscriptionRequest, KeywordSubscriptionPage, KeywordSubscriptionResponse,
)
from service.auth import AuthError
from service.keyword_subscriptions import KeywordSubscriptionService
from service.text_analysis_profiles import active_policy


def unavailable():
    return AuthError(503, 'KEYWORD_ANALYSIS_UNAVAILABLE', headers={'Retry-After': '5'})


class KeywordCreateRoute(ProtectedRoute):
    async def prepare_request(self, request):
        try:
            body = CreateKeywordSubscriptionRequest.model_validate(await request.json())
        except ValidationError as exc:
            errors = [{**error, 'loc': ('body', *error['loc'])} for error in exc.errors()]
            raise RequestValidationError(errors) from None
        await KeywordSubscriptionService(request).check_duplicate(body.keyword)
        runtime = getattr(request.app.state, 'text_analysis_runtime', None)
        if runtime is None:
            raise unavailable()
        try:
            _, profile = await active_policy(request.state.db, runtime.profile)
        except AnalysisError:
            raise unavailable() from None
        request.state.keyword_body = body
        request.state.keyword_profile_id = profile.id
        request.state.keyword_runtime = runtime

    async def prepare_outside_transaction(self, request):
        value = AnalysisInput(description=request.state.keyword_body.keyword)
        try:
            result = await request.state.keyword_runtime.analyze(value)
        except AnalysisError:
            raise unavailable() from None
        if result.source_hash != value.source_hash:
            raise unavailable()
        terms = atomic_terms(result.keywords)
        if not terms:
            raise AuthError(400, 'VALIDATION_ERROR', fields=[
                {'field': 'keyword', 'code': 'NO_MATCHABLE_TERMS'},
            ])
        request.state.keyword_analysis = result
        request.state.keyword_terms = terms


router = APIRouter(
    tags=['keyword_subscriptions'], route_class=ProtectedRoute,
    responses={code: {'model': ErrorResponse} for code in (400, 401, 403, 415, 500)},
)


@router.get('/me/keyword-subscriptions', response_model=KeywordSubscriptionPage,
            summary='내 키워드 구독 목록')
async def list_keyword_subscriptions(request: Request, params: Annotated[KeywordSubscriptionParams, Query()]):
    return await KeywordSubscriptionService(request).list(params)


async def create_keyword_subscription(request: Request, body: CreateKeywordSubscriptionRequest, response: Response):
    try:
        result = await KeywordSubscriptionService(request).create(
            body, request.state.keyword_analysis, request.state.keyword_terms,
            request.state.keyword_profile_id, request.state.keyword_runtime.profile,
        )
    except AnalysisError:
        raise unavailable() from None
    response.headers['Location'] = f'/api/v1/me/keyword-subscriptions/{result.subscription_id}'
    return result


router.add_api_route(
    '/me/keyword-subscriptions', create_keyword_subscription, methods=['POST'], status_code=201,
    response_model=KeywordSubscriptionResponse, route_class_override=KeywordCreateRoute,
    summary='키워드 구독', responses={409: {'model': ErrorResponse}, 503: {'model': ErrorResponse}},
)


@router.delete('/me/keyword-subscriptions/{subscriptionId}', status_code=204,
               summary='키워드 구독 해제', responses={404: {'model': ErrorResponse}})
async def delete_keyword_subscription(request: Request, subscriptionId: UUID):
    await KeywordSubscriptionService(request).delete(subscriptionId)
    return Response(status_code=204)
