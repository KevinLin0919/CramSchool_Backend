"""Bearer-token authentication.

Opaque random tokens, stored only as SHA-256, one per device. Deliberately not
JWT: the operation this system actually needs is "a teacher lost their iPad,
lock it out now", and a self-contained token cannot be revoked without building
the very lookup table that an opaque token already is.

SHA-256 rather than a slow password hash is correct here *because* the token is
256 bits of `secrets` output — there is no dictionary to attack, so the reason
to use bcrypt/argon2 (making guesses expensive) does not apply, and a fast hash
keeps the lookup a single indexed query.
"""

from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import get_db
from .models import ApiToken, Teacher

TOKEN_BYTES = 32


def generate_token() -> str:
    return secrets.token_urlsafe(TOKEN_BYTES)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _extract_bearer(authorization: str | None) -> str:
    if not authorization:
        raise _unauthorized("缺少認證資訊")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise _unauthorized("認證格式錯誤，應為 Bearer token")
    return token.strip()


def current_token(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> ApiToken:
    """The credential the caller presented, not just who it belongs to.

    Split out from `current_teacher` because signing out has to revoke *this*
    device and nothing else. Teachers carry an iPad and a phone, and killing
    the phone because the iPad changed hands is not signing out — it is an
    outage with a friendly label on it.
    """
    token = _extract_bearer(authorization)
    now = datetime.now(UTC)

    row = db.execute(
        select(ApiToken).where(ApiToken.token_hash == hash_token(token))
    ).scalar_one_or_none()

    if row is None or row.revoked_at is not None:
        raise _unauthorized("token 無效或已撤銷")
    if row.expires_at is not None and row.expires_at < now:
        raise _unauthorized("token 已過期")

    if row.teacher is None or not row.teacher.is_active:
        raise _unauthorized("帳號已停用")

    # Cheap enough to write every request, and it is what makes an unused
    # device visible in `cramctl tokens` before it becomes a stale credential.
    row.last_used_at = now
    db.commit()
    return row


def current_teacher(token: ApiToken = Depends(current_token)) -> Teacher:
    return token.teacher


def require_admin(teacher: Teacher = Depends(current_teacher)) -> Teacher:
    if teacher.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理員權限")
    return teacher
