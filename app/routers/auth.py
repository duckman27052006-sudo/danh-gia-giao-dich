from __future__ import annotations

import time
from collections import defaultdict

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit import log_action
from app.config import settings
from app.db import get_db
from app.deps import client_meta, get_current_user
from app.models import AuditLog, User, utcnow
from app.schemas import LoginRequest, TokenResponse, UserOut
from app.security import (
    consume_refresh_token,
    create_access_token,
    issue_refresh_token,
    revoke_all_sessions,
    revoke_refresh_token,
    verify_password,
)

router = APIRouter(prefix="/auth", tags=["auth"])

REFRESH_COOKIE = "fl_refresh"
WINDOW_SECONDS = 300
MAX_ATTEMPTS = 6
_failures: dict[str, list[float]] = defaultdict(list)


def _rate_limited(key: str) -> bool:
    now = time.time()
    attempts = [stamp for stamp in _failures[key] if now - stamp < WINDOW_SECONDS]
    _failures[key] = attempts
    return len(attempts) >= MAX_ATTEMPTS


def _record_failure(key: str) -> None:
    _failures[key].append(time.time())


def _set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.refresh_token_days * 86400,
        path="/api/auth",
    )


def _token_response(user: User, response: Response, db: Session, request: Request) -> TokenResponse:
    access_token, expires_in = create_access_token(user)
    ip, user_agent = client_meta(request)
    refresh = issue_refresh_token(db, user, ip, user_agent)
    _set_refresh_cookie(response, refresh)
    return TokenResponse(access_token=access_token, expires_in=expires_in, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    ip, _ = client_meta(request)
    key = f"{payload.email.lower()}|{ip}"
    if _rate_limited(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Quá nhiều lần đăng nhập thất bại, thử lại sau 5 phút")

    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if user is None or not verify_password(payload.password, user.password_hash):
        _record_failure(key)
        db.add(
            AuditLog(
                actor_email=payload.email.lower(),
                action="auth.login_failed",
                entity_type="auth",
                entity_id=payload.email.lower(),
                ip=ip,
            )
        )
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Email hoặc mật khẩu không đúng")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Tài khoản đã bị vô hiệu hoá")

    user.last_login_at = utcnow()
    log_action(db, actor=user, action="auth.login", entity_type="auth", entity_id=user.id, request=request)
    token_response = _token_response(user, response, db, request)
    _failures.pop(key, None)
    db.commit()
    return token_response


@router.post("/refresh", response_model=TokenResponse)
def refresh(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Không có phiên làm việc")
    user = consume_refresh_token(db, raw)
    return _token_response(user, response, db, request)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(request: Request, db: Session = Depends(get_db)) -> Response:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        revoke_refresh_token(db, raw)
    # Xoá cookie trên CHÍNH object được trả về: header set trên `Response` do
    # FastAPI inject (tham số `response: Response`) bị bỏ khi handler return một
    # `Response` khác, nên trước đây cookie refresh không bao giờ bị xoá.
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return response


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    revoke_all_sessions(db, user.id)
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    return response
