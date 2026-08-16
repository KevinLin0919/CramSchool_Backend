from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import ApiToken, InviteCode, Teacher
from ..schemas import TeacherOut, TokenRequest, TokenResponse
from ..security import current_teacher, generate_token, hash_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/token", response_model=TokenResponse, summary="以邀請碼換取裝置 token")
def redeem_invite(payload: TokenRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Enrolment: an admin issues a single-use code, the device swaps it for a token.

    Teachers never type a password on a phone keyboard, and the code being
    single-use means an overheard one is worthless the moment it is redeemed.
    """
    invite = db.execute(
        select(InviteCode).where(InviteCode.code_hash == hash_token(payload.invite_code.strip()))
    ).scalar_one_or_none()

    now = datetime.now(UTC)
    if invite is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀請碼無效")
    if invite.redeemed_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀請碼已被使用")
    if invite.expires_at is not None and invite.expires_at < now:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀請碼已過期")

    teacher = invite.teacher
    if teacher is None or not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="帳號已停用")

    raw = generate_token()
    db.add(
        ApiToken(
            teacher_id=teacher.id,
            token_hash=hash_token(raw),
            device_name=payload.device_name,
        )
    )
    invite.redeemed_at = now
    db.commit()

    # The only time the raw token is ever transmitted. Nothing stores it.
    return TokenResponse(
        token=raw,
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        role=teacher.role,
        expires_at=None,
    )


@router.get("/me", response_model=TeacherOut, summary="確認目前 token 對應的帳號")
def whoami(teacher: Teacher = Depends(current_teacher)) -> Teacher:
    return teacher


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="撤銷目前裝置的 token")
def logout(
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(current_teacher),
) -> None:
    """Revokes every token for this teacher's account.

    Coarser than revoking just the calling device, and that is the intent: the
    reason a teacher reaches for this is a lost iPad, when the token they most
    need dead is the one they cannot present.
    """
    now = datetime.now(UTC)
    for token in teacher.tokens:
        if token.revoked_at is None:
            token.revoked_at = now
    db.commit()
