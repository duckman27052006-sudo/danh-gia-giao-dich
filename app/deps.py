from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User
from app.security import decode_access_token

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Chưa đăng nhập")
    payload = decode_access_token(credentials.credentials)
    user = db.get(User, payload.get("sub"))
    if user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Tài khoản không khả dụng")
    return user


def require_roles(*roles: str) -> Callable[..., User]:
    def dependency(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Bạn không có quyền thực hiện thao tác này")
        return user

    return dependency


def client_meta(request: Request) -> tuple[str, str]:
    """IP dùng cho audit/rate-limit.

    Chỉ đọc ``X-Forwarded-For`` khi TRUST_PROXY_HEADERS=true — nếu không, kẻ tấn công
    có thể gửi header giả để né rate-limit đăng nhập.
    """
    ip = ""
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip() if forwarded else ""
    if not ip and request.client is not None:
        ip = request.client.host
    return ip, request.headers.get("user-agent", "")[:255]
