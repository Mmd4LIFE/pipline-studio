from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.errors import AppError
from app.models import User
from app.security import csrf_ok, read_session_token


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def current_user(
    request: Request,
    db: Session = Depends(get_db),
    x_csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> User:
    settings = get_settings()
    token = request.cookies.get(settings.studio_session_cookie)
    user_id = read_session_token(token) if token else None
    if not user_id:
        raise AppError("permission_denied", "Authentication required", 401)
    user = db.get(User, user_id)
    if not user or user.disabled_at is not None:
        raise AppError("permission_denied", "Authentication required", 401)
    if request.method not in SAFE_METHODS:
        csrf_cookie = request.cookies.get(settings.studio_csrf_cookie)
        if not csrf_ok(csrf_cookie, x_csrf_token):
            raise AppError("permission_denied", "CSRF token missing or invalid", 403)
    return user


def require_editor(user: User = Depends(current_user)) -> User:
    if user.role not in {"admin", "editor"}:
        raise AppError("permission_denied", "Editor role required", 403)
    return user
