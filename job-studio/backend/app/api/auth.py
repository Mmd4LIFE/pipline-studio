from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.errors import AppError
from app.models import User
from app.schemas.auth import LoginRequest, UserOut
from app.security import (
    clear_auth_cookies,
    issue_session_token,
    new_csrf_token,
    set_auth_cookies,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or user.disabled_at is not None or not verify_password(payload.password, user.password_hash):
        raise AppError("permission_denied", "Invalid email or password", 401)
    set_auth_cookies(response, issue_session_token(user.id), new_csrf_token())
    return UserOut(id=user.id, email=user.email, role=user.role)


@router.post("/logout")
def logout(response: Response):
    clear_auth_cookies(response)
    return {"ok": True}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return UserOut(id=user.id, email=user.email, role=user.role)
