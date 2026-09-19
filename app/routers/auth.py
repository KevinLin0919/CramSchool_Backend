import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth_microsoft import MicrosoftAuthError, NotEnrolled, TokenVerifier
from ..config import Settings, get_settings
from ..db import get_db
from ..models import ApiToken, InviteCode, Teacher
from ..ratelimit import RateLimiter, client_key
from ..schemas import MicrosoftTokenRequest, TeacherOut, TokenRequest, TokenResponse
from ..security import current_teacher, current_token, generate_token, hash_token

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# One line per device that successfully enrols or signs in.
#
# uvicorn's access log already records every request's method, path and
# status, so failures and 429s are visible there. What it cannot show is WHO
# — and "which account is this device carrying" is the question actually
# worth answering later, when a token turns up somewhere it should not be or
# a teacher says they never signed in on that iPad.
#
# Never the token, never the invite code, never the Microsoft ID token. A log
# that records a credential has turned a rotated file into a second copy of
# the thing it was protecting.
log = logging.getLogger("cramschool.auth")

# The two endpoints below are the only ones in this service that answer a
# caller who has presented nothing. Everything else is behind a 256-bit token,
# so this is not guarding a secret — it is bounding how much work a stranger
# can make this machine do while a teacher is in the middle of a stack.
#
# Built once at import, because a limiter rebuilt per request counts nothing.
_settings = get_settings()
_auth_limit = RateLimiter(
    per_key=_settings.auth_rate_limit_per_ip,
    overall=_settings.auth_rate_limit_overall,
    window_seconds=_settings.auth_rate_limit_window_seconds,
)


def rate_limited(request: Request, settings: Settings = Depends(get_settings)) -> None:
    _auth_limit.check(client_key(request, settings.trusted_proxies))


@router.post("/token", response_model=TokenResponse, summary="以邀請碼換取裝置 token",
             dependencies=[Depends(rate_limited)])
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

    log.info("enrolled teacher_id=%s role=%s device=%r via=invite",
             teacher.id, teacher.role, payload.device_name)

    # The only time the raw token is ever transmitted. Nothing stores it.
    return TokenResponse(
        token=raw,
        teacher_id=teacher.id,
        teacher_name=teacher.name,
        role=teacher.role,
        expires_at=None,
    )


@router.post("/microsoft", response_model=TokenResponse,
             summary="以學校的 Microsoft 帳號換取裝置 token",
             dependencies=[Depends(rate_limited)])
def sign_in_with_microsoft(payload: MicrosoftTokenRequest,
                           db: Session = Depends(get_db),
                           settings: Settings = Depends(get_settings)) -> TokenResponse:
    """Microsoft replaces the invite code, and nothing else.

    What comes back is the same device token the invite-code path issues, so
    everything downstream — the Keychain, the bearer header, per-device
    revocation — is untouched by which door someone came through.

    Unlike that path, these tokens expire. A device token that outlives the
    account it was issued against would make the central-offboarding argument
    for using Entra at all a false one: disabling someone in the directory has
    to eventually stop the iPad in their bag.
    """
    verifier = TokenVerifier(settings)
    try:
        identity = verifier.verify(payload.id_token)
    except MicrosoftAuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc

    teacher = db.execute(
        select(Teacher).where(Teacher.microsoft_oid == identity.oid)
    ).scalar_one_or_none()

    if teacher is None and identity.email:
        # First sign-in for someone an admin already created by email. Claim
        # the row rather than making a second one for the same person.
        teacher = db.execute(
            select(Teacher).where(Teacher.email == identity.email)
        ).scalar_one_or_none()
        if teacher is not None:
            teacher.microsoft_oid = identity.oid

    if teacher is None:
        if not settings.microsoft_auto_provision:
            # Being in the directory is not the same as being a teacher, and
            # this service stores every answer key in the school.
            raise HTTPException(status_code=NotEnrolled.status_code,
                                detail=NotEnrolled.detail)
        teacher = Teacher(name=identity.name,
                          email=identity.email or None,
                          microsoft_oid=identity.oid)
        db.add(teacher)
        db.flush()

    if not teacher.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="帳號已停用")

    # Directory attributes are the source of truth for these; someone who
    # changes their name should not stay under the old one forever.
    teacher.name = identity.name or teacher.name
    if identity.email:
        teacher.email = identity.email

    raw = generate_token()
    expires = datetime.now(UTC) + timedelta(days=settings.microsoft_token_days)
    db.add(ApiToken(teacher_id=teacher.id,
                    token_hash=hash_token(raw),
                    device_name=payload.device_name,
                    expires_at=expires))
    db.commit()

    log.info("signed in teacher_id=%s role=%s device=%r via=microsoft expires=%s",
             teacher.id, teacher.role, payload.device_name, expires.isoformat())

    return TokenResponse(token=raw,
                         teacher_id=teacher.id,
                         teacher_name=teacher.name,
                         role=teacher.role,
                         expires_at=expires)


@router.get("/me", response_model=TeacherOut, summary="確認目前 token 對應的帳號")
def whoami(teacher: Teacher = Depends(current_teacher)) -> Teacher:
    return teacher


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT,
             summary="撤銷目前這台裝置的 token")
def logout(
    db: Session = Depends(get_db),
    token: ApiToken = Depends(current_token),
) -> None:
    """Signs this device out, and only this device.

    This used to revoke every token on the account, justified by the lost-iPad
    case — the one token you most need dead is the one you cannot present. That
    case is real but it belongs to the admin side, where `cramctl tokens revoke`
    already handles it: the person who lost the device is, by definition, not
    holding it.

    What the app actually calls this for is ordinary: signing in as the wrong
    account, or handing a shared iPad to the next teacher. Teachers carry more
    than one device, so account-wide revocation here would log them out of a
    phone they never touched. `/logout/all` keeps that behaviour for when it is
    genuinely wanted.
    """
    if token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
        db.commit()


@router.post("/logout/all", status_code=status.HTTP_204_NO_CONTENT,
             summary="撤銷這個帳號的所有裝置")
def logout_all(
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(current_teacher),
) -> None:
    """Every device on the account, for when one of them is gone.

    Destructive enough to deserve its own name rather than being what happens
    when someone taps 登出.
    """
    now = datetime.now(UTC)
    for token in teacher.tokens:
        if token.revoked_at is None:
            token.revoked_at = now
    db.commit()
