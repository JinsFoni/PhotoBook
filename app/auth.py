"""认证 — argon2 密码 + 服务端 session + HttpOnly Cookie。"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .db import Session as DbSession
from .db import User
from .database import get_db

ph = PasswordHasher()
COOKIE_NAME = "pb_session"


def hash_password(plain: str) -> str:
    return ph.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return ph.verify(hashed, plain)
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def create_session(s: Session, user_id: int) -> str:
    sid = secrets.token_urlsafe(32)
    s.add(DbSession(id=sid, user_id=user_id,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_ttl_hours)))
    return sid


def destroy_session(s: Session, sid: str) -> None:
    row = s.get(DbSession, sid)
    if row:
        s.delete(row)


def current_user(request: Request, s: Session = Depends(get_db)) -> User | None:
    sid = request.cookies.get(COOKIE_NAME)
    if not sid:
        return None
    sess = s.get(DbSession, sid)
    if not sess:
        return None
    expires = sess.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < datetime.now(timezone.utc):
        s.delete(sess)
        return None
    return s.get(User, sess.user_id)


def require_login(user: User | None = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def require_admin(user: User | None = Depends(current_user)) -> User:
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin required")
    return user


def all_usernames(s: Session) -> list[str]:
    return list(s.scalars(select(User.username)).all())
