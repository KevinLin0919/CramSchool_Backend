"""Verification of Microsoft Entra ID tokens.

An ID token is a bearer assertion signed by Microsoft. Trusting one means
checking, in order: that the signature is genuine, that the key it was signed
with is currently published by the tenant we care about, and that every claim
naming a recipient names *us*. Skip any of those and the endpoint accepts
tokens it has no business accepting.

Three of the checks here exist because of specific, well-known attacks rather
than general caution:

* **`alg` is pinned to RS256.** A token whose header says `none` carries no
  signature at all, and a library that honours the header will happily verify
  it. The sibling attack swaps RS256 for HS256 so the *public* key — which is
  published — becomes the HMAC secret. Passing an explicit algorithm list is
  what closes both, and it is why this goes through PyJWT rather than
  hand-rolled verification.

* **`aud` must be our client id.** Any application registered in the same
  tenant can obtain a valid, correctly-signed token for its own audience. If
  we do not check who the token was minted for, one of those is enough to sign
  in as its holder.

* **`tid` must be the school's tenant.** Without it, a correctly-signed token
  from any Microsoft organisation in the world passes — the signature proves
  Microsoft issued it, not that it came from anyone we know.
"""

from __future__ import annotations

import time
import urllib.request
from dataclasses import dataclass

import jwt
from jwt import PyJWKClient

from .config import Settings

# Microsoft rotates signing keys. Everything below exists so that rotation
# does not sign everyone out, without letting an unknown `kid` become a way to
# make us fetch on demand.
_MIN_REFRESH_INTERVAL = 60.0

# Clock skew tolerance on exp/nbf/iat. Small: a phone and a server that
# disagree by more than a minute have a different problem.
_LEEWAY_SECONDS = 60


class MicrosoftAuthError(Exception):
    """Base for anything that means "do not trust this token"."""

    status_code = 401
    detail = "Microsoft 授權無效"


class NotConfigured(MicrosoftAuthError):
    status_code = 503
    detail = "尚未設定 Microsoft 登入"


class InvalidToken(MicrosoftAuthError):
    status_code = 401
    detail = "Microsoft 授權無效或已過期"


class WrongTenant(MicrosoftAuthError):
    status_code = 403
    detail = "這個帳號不屬於浮島"


class NotEnrolled(MicrosoftAuthError):
    status_code = 403
    detail = "這個帳號還不是老師帳號，請聯絡管理員"


@dataclass(frozen=True)
class MicrosoftIdentity:
    """The parts of a verified token this service acts on."""

    oid: str
    tenant_id: str
    name: str
    email: str


class KeyStore:
    """Microsoft's published signing keys, cached.

    A `kid` that is not in the cache is the normal signal that keys rotated,
    so it triggers exactly one refresh — but no more often than
    `_MIN_REFRESH_INTERVAL`, so a stream of tokens carrying invented key ids
    cannot turn into a stream of outbound requests.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client: PyJWKClient | None = None
        self._loaded_at = 0.0
        self._last_refresh_attempt = 0.0

    def _build(self) -> PyJWKClient:
        return PyJWKClient(self._settings.microsoft_jwks_url, cache_keys=False)

    def signing_key(self, token: str):
        now = time.monotonic()
        expired = now - self._loaded_at > self._settings.jwks_cache_seconds
        if self._client is None or expired:
            self._client = self._build()
            self._loaded_at = now

        try:
            return self._client.get_signing_key_from_jwt(token).key
        except Exception:
            # Either the keys rotated or the kid is nonsense. One retry
            # distinguishes them; the interval stops the second case being
            # free to an attacker.
            if now - self._last_refresh_attempt < _MIN_REFRESH_INTERVAL:
                raise InvalidToken from None
            self._last_refresh_attempt = now
            self._client = self._build()
            self._loaded_at = now
            try:
                return self._client.get_signing_key_from_jwt(token).key
            except Exception as exc:
                raise InvalidToken from exc


class TokenVerifier:
    """Turns an ID token into an identity, or raises."""

    def __init__(self, settings: Settings, keys: KeyStore | None = None) -> None:
        self._settings = settings
        self._keys = keys or KeyStore(settings)

    def verify(self, id_token: str) -> MicrosoftIdentity:
        settings = self._settings
        if not settings.microsoft_configured:
            raise NotConfigured

        key = self._keys.signing_key(id_token)

        try:
            claims = jwt.decode(
                id_token,
                key=key,
                # Explicit, and only one. The header's own `alg` is an
                # attacker-controlled field; honouring it is the bug.
                algorithms=["RS256"],
                audience=settings.microsoft_client_id,
                issuer=settings.microsoft_issuer,
                leeway=_LEEWAY_SECONDS,
                options={
                    "require": ["exp", "iat", "aud", "iss", "sub"],
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_nbf": True,
                    "verify_iat": True,
                    "verify_aud": True,
                    "verify_iss": True,
                },
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidToken from exc

        # `iss` already pins the tenant for the v2.0 endpoint, but the claim is
        # checked on its own too: the two are configured from the same value,
        # and a future issuer format that stops embedding the tenant would
        # silently widen who gets in.
        tenant = str(claims.get("tid") or "")
        if tenant != settings.microsoft_tenant_id:
            raise WrongTenant

        oid = str(claims.get("oid") or "")
        if not oid:
            # Without a stable subject there is nothing to key an account on,
            # and falling back to email would key it on something that changes.
            raise InvalidToken

        email = str(
            claims.get("preferred_username")
            or claims.get("email")
            or ""
        ).strip().lower()
        name = str(claims.get("name") or email or "未命名").strip()

        return MicrosoftIdentity(oid=oid, tenant_id=tenant, name=name, email=email)


def fetch_discovery_document(settings: Settings, timeout: float = 5.0) -> dict:
    """The tenant's OIDC metadata — for `cramctl` to check a registration.

    Not used at sign-in: the endpoints are derived from the tenant id, and one
    fewer network call on the hot path is one fewer way for signing in to fail.
    """
    url = (f"https://login.microsoftonline.com/{settings.microsoft_tenant_id}"
           "/v2.0/.well-known/openid-configuration")
    import json

    with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
        return json.load(response)
