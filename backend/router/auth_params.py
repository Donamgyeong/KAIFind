"""Header/cookie parameters; session and CSRF validation belongs to services."""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Cookie, Header


@dataclass(kw_only=True)
class AuthParams:
    # Unsupported languages fall back to Korean in the error translation layer.
    accept_language: Annotated[str | None, Header(alias="Accept-Language")] = None


@dataclass(kw_only=True)
class CsrfParams(AuthParams):
    session: Annotated[str | None, Cookie(alias="KAIFIND_SESSION")] = None


@dataclass(kw_only=True)
class SessionParams(AuthParams):
    session: Annotated[str, Cookie(alias="KAIFIND_SESSION", min_length=1)]


@dataclass(kw_only=True)
class LogoutParams(SessionParams):
    csrf_token: Annotated[str, Header(alias="X-CSRF-Token", min_length=1)]
    origin: Annotated[str | None, Header(alias="Origin")] = None


@dataclass(kw_only=True)
class MockLoginParams(LogoutParams):
    content_type: Annotated[str, Header(alias="Content-Type")]
