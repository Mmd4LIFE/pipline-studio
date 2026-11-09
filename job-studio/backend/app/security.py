from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from fastapi import Response

from app.config import get_settings

hasher = PasswordHasher()
SESSION_TTL_SECONDS = 60 * 60 * 12


def hash_password(password: str) -> str:
    return hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return hasher.verify(password_hash, password)
    except Exception:
        return False


def _serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_settings().studio_secret_key, salt="studio-session")


def issue_session_token(user_id: str) -> str:
    return _serializer().dumps({"uid": user_id, "nonce": secrets.token_hex(8)})


def read_session_token(token: str) -> str | None:
    try:
        data = _serializer().loads(token, max_age=SESSION_TTL_SECONDS)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return None
    uid = data.get("uid")
    return str(uid) if uid else None


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def csrf_ok(cookie_token: str | None, header_token: str | None) -> bool:
    if not cookie_token or not header_token:
        return False
    return hmac.compare_digest(cookie_token, header_token)


def set_auth_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    settings = get_settings()
    cookie_kw = {
        "httponly": True,
        "secure": False,
        "samesite": "lax",
        "max_age": SESSION_TTL_SECONDS,
        "path": "/",
    }
    response.set_cookie(settings.studio_session_cookie, session_token, **cookie_kw)
    response.set_cookie(
        settings.studio_csrf_cookie,
        csrf_token,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=SESSION_TTL_SECONDS,
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.studio_session_cookie, path="/")
    response.delete_cookie(settings.studio_csrf_cookie, path="/")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def later(seconds: int) -> datetime:
    return utcnow() + timedelta(seconds=seconds)
