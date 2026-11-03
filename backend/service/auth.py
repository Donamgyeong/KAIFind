"""Server-side Auth sessions. All state changes use PostgreSQL transactions."""
import base64
import hashlib
import hmac
import math
import os
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Callable

from Crypto.Cipher import AES
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from library.database import session_factory
from model import Session, User
from model.entities import AuthLoginRate
from schema.auth import AuthUserResponse, SessionInfo

COOKIE = 'KAIFIND_SESSION'
IDLE = timedelta(minutes=30)
ABSOLUTE = timedelta(hours=12)


class AuthError(Exception):
    def __init__(self, status, code, *, fields=None, clear_cookie=False, headers=None):
        self.status, self.code = status, code
        self.fields = fields or []
        self.clear_cookie = clear_cookie
        self.headers = headers or {}


@dataclass(frozen=True)
class MockAccount:
    key: str
    subject: str
    name: str
    email: str
    affiliation: str
    role: str = 'MEMBER'
    active: bool = True


DEFAULT_ACCOUNTS = (
    MockAccount('student-01', 'mock:student-01', '테스트 학생 1', 'student01@example.com', 'STUDENT'),
    MockAccount('faculty-01', 'mock:faculty-01', '테스트 교수 1', 'faculty01@example.com', 'FACULTY'),
    MockAccount('admin-01', 'mock:admin-01', '테스트 관리자', 'admin01@example.com', 'STAFF', 'ADMIN'),
)


@dataclass(frozen=True)
class AuthSettings:
    environment: str = 'production'
    mock_enabled: bool = False
    encryption_key: bytes = b''
    allowed_origins: tuple[str, ...] = ()
    accounts: tuple[MockAccount, ...] = DEFAULT_ACCOUNTS

    @property
    def allow_mock(self):
        return self.mock_enabled and self.environment in {'local', 'test', 'demo'}

    def key(self):
        if len(self.encryption_key) != 32:
            raise RuntimeError('AUTH_ENCRYPTION_KEY must contain a base64-encoded 32-byte key')
        return self.encryption_key


@lru_cache
def get_settings():
    raw = os.getenv('AUTH_ENCRYPTION_KEY', '')
    return AuthSettings(
        environment=os.getenv('APP_ENV', 'production'),
        mock_enabled=os.getenv('MOCK_AUTH_ENABLED', '').lower() == 'true',
        encryption_key=base64.b64decode(raw, validate=True) if raw else b'',
        allowed_origins=tuple(x.strip() for x in os.getenv('AUTH_ALLOWED_ORIGINS', '').split(',') if x.strip()),
    )


@dataclass
class AuthRuntime:
    settings: AuthSettings
    factory: Callable = field(default=lambda: session_factory()())
    clock: Callable = field(default=lambda: datetime.now(timezone.utc))


def runtime(request):
    configured = getattr(request.app.state, 'auth_runtime', None)
    return configured if configured is not None else AuthRuntime(get_settings())


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def set_cookie(response, token):
    response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite='lax', path='/')


def clear_cookie(response):
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='lax', path='/')


class AuthService:
    def __init__(self, rt):
        self.rt = rt
        self.settings = rt.settings

    def encrypt(self, token):
        cipher = AES.new(self.settings.key(), AES.MODE_GCM)
        encrypted, tag = cipher.encrypt_and_digest(token.encode())
        return base64.b64encode(cipher.nonce + tag + encrypted).decode()

    def decrypt(self, value):
        raw = base64.b64decode(value, validate=True)
        cipher = AES.new(self.settings.key(), AES.MODE_GCM, nonce=raw[:16])
        return cipher.decrypt_and_verify(raw[32:], raw[16:32]).decode()

    def new_session(self, db, now, user_id=None):
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        row = Session(token_hash=token_hash(token), user_id=user_id,
            csrf_secret_ciphertext=self.encrypt(csrf), created_at=now,
            last_activity_at=now, idle_expires_at=now + IDLE, absolute_expires_at=now + ABSOLUTE)
        db.add(row)
        return row, token, csrf

    async def lookup(self, db, token):
        if not token:
            return None
        return await db.scalar(select(Session).where(Session.token_hash == token_hash(token)).with_for_update())

    @staticmethod
    def expired(row, now):
        return now >= row.idle_expires_at or now >= row.absolute_expires_at

    def require_csrf(self, row, csrf, now):
        if row is None or self.expired(row, now) or not csrf:
            raise AuthError(403, 'CSRF_INVALID')
        if not hmac.compare_digest(self.decrypt(row.csrf_secret_ciphertext).encode(), csrf.encode()):
            raise AuthError(403, 'CSRF_INVALID')

    async def csrf(self, cookie):
        async with self.rt.factory() as db, db.begin():
            row = await self.lookup(db, cookie)
            now = self.rt.clock()
            if row is not None and not self.expired(row, now):
                return self.decrypt(row.csrf_secret_ciphertext), None
            if row is not None:
                await db.delete(row)
            _, token, csrf = self.new_session(db, now)
            return csrf, token

    async def accounts(self):
        active = [a for a in self.settings.accounts if a.active]
        if not active:
            return []
        async with self.rt.factory() as db:
            users = (await db.scalars(select(User).where(User.mock_subject.in_([a.subject for a in active])))).all()
        roles = {u.mock_subject: u.role for u in users}
        return [dict(mockAccountId=a.key, displayName=a.name, affiliation=a.affiliation,
                     role=roles.get(a.subject, a.role)) for a in active]

    async def login(self, cookie, csrf, account_key):
        account = next((a for a in self.settings.accounts if a.key == account_key and a.active), None)
        async with self.rt.factory() as db, db.begin():
            old = await self.lookup(db, cookie)
            now = self.rt.clock()
            self.require_csrf(old, csrf, now)
            if account is None:
                raise AuthError(401, 'INVALID_MOCK_ACCOUNT')
            # ON CONFLICT waits for competing inserts and preserves administrator changes.
            created = await db.scalar(insert(User).values(mock_subject=account.subject,
                name=account.name, email=account.email, affiliation=account.affiliation,
                role=account.role, language='ko').on_conflict_do_nothing(
                    index_elements=[User.mock_subject]).returning(User.id))
            user = await db.scalar(select(User).where(User.mock_subject == account.subject))
            await db.delete(old)
            row, token, new_csrf = self.new_session(db, now, user.id)
            payload = dict(user=self.user_payload(user), isNewUser=created is not None,
                session=SessionInfo.model_validate(dict(idleTimeoutSeconds=1800,
                    idleExpiresAt=row.idle_expires_at, absoluteExpiresAt=row.absolute_expires_at)),
                csrfToken=new_csrf)
        return payload, token

    @staticmethod
    def user_payload(user):
        return AuthUserResponse.model_validate(dict(userId=user.id, name=user.name, email=user.email,
            affiliation=user.affiliation, role=user.role, language=user.language))

    async def me(self, cookie):
        error = None
        async with self.rt.factory() as db, db.begin():
            row = await self.lookup(db, cookie)
            now = self.rt.clock()
            if row is None:
                error = AuthError(401, 'AUTH_REQUIRED')
            elif self.expired(row, now):
                await db.delete(row)
                error = AuthError(401, 'SESSION_EXPIRED', clear_cookie=True)
            elif row.user_id is None:
                error = AuthError(401, 'AUTH_REQUIRED')
            else:
                user = await db.get(User, row.user_id)
                if user is None:
                    await db.delete(row)
                    error = AuthError(401, 'AUTH_REQUIRED', clear_cookie=True)
                else:
                    row.last_activity_at = now
                    row.idle_expires_at = min(now + IDLE, row.absolute_expires_at)
                    payload = self.user_payload(user)
        # Raise after commit so expired sessions really are removed.
        if error:
            raise error
        return payload

    async def logout(self, cookie, csrf):
        async with self.rt.factory() as db, db.begin():
            row = await self.lookup(db, cookie)
            self.require_csrf(row, csrf, self.rt.clock())
            await db.delete(row)

    async def rate_limit(self, ip):
        now = self.rt.clock()
        key = token_hash(ip)
        async with self.rt.factory() as db, db.begin():
            # Shared across workers, atomic even for the first request by this IP.
            await db.execute(text('SELECT pg_advisory_xact_lock(:key)'),
                             {'key': int(key[:15], 16)})
            await db.execute(delete(AuthLoginRate).where(AuthLoginRate.window_started_at <= now - timedelta(minutes=1)))
            row = await db.get(AuthLoginRate, key, with_for_update=True)
            if row is None:
                db.add(AuthLoginRate(ip_hash=key, window_started_at=now, attempts=1))
            elif row.attempts >= 30:
                retry = max(1, math.ceil((row.window_started_at + timedelta(minutes=1) - now).total_seconds()))
                raise AuthError(429, 'RATE_LIMITED', headers={'Retry-After': str(retry)})
            else:
                row.attempts += 1
