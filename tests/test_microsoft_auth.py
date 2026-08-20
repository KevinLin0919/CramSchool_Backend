"""Security tests for Microsoft sign-in.

Every test here mints its own tokens with a key pair generated in the test and
serves its own JWKS, so the whole verifier is exercised without a tenant, a
network, or a real account. That is the point: the rules being checked are the
ones that decide whether a stranger's token opens the school's answer keys,
and they should not first be exercised in front of a class.

The negative cases are not hypothetical. `alg: none` and RS256→HS256 confusion
are the two classic ways an OIDC integration becomes forgeable, and both look
like a perfectly ordinary token until something explicitly refuses them.
"""

import json
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth_microsoft import (
    InvalidToken,
    NotConfigured,
    TokenVerifier,
    WrongTenant,
)
from app.config import Settings
from app.db import SessionLocal
from app.models import ApiToken, Teacher

TENANT = "11111111-2222-3333-4444-555555555555"
CLIENT = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
OID = "99999999-8888-7777-6666-555555555555"
KID = "test-key-1"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


@pytest.fixture
def settings():
    return Settings(microsoft_tenant_id=TENANT, microsoft_client_id=CLIENT,
                    microsoft_auto_provision=False)


class StubKeyStore:
    """Stands in for Microsoft's published keys."""

    def __init__(self, public_key, fail: bool = False):
        self._key = public_key
        self._fail = fail
        self.lookups = 0

    def signing_key(self, token: str):
        self.lookups += 1
        if self._fail:
            raise InvalidToken
        return self._key


def make_token(private, *, alg="RS256", key=None, **overrides) -> str:
    now = int(time.time())
    claims = {
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0",
        "aud": CLIENT,
        "tid": TENANT,
        "oid": OID,
        "sub": "subject-abc",
        "name": "王老師",
        "preferred_username": "wang@fudao.example",
        "iat": now,
        "nbf": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    for k in [k for k, v in claims.items() if v is None]:
        del claims[k]
    return jwt.encode(claims, key if key is not None else private,
                      algorithm=alg, headers={"kid": KID})


def verifier_for(settings, keypair, **kw):
    _, public = keypair
    return TokenVerifier(settings, keys=StubKeyStore(public, **kw))


# ── 正常路徑 ─────────────────────────────────────────────────────────────────


def test_valid_token_yields_identity(settings, keypair):
    private, _ = keypair
    identity = verifier_for(settings, keypair).verify(make_token(private))
    assert identity.oid == OID
    assert identity.tenant_id == TENANT
    assert identity.name == "王老師"
    assert identity.email == "wang@fudao.example"


def test_email_is_lowercased(settings, keypair):
    private, _ = keypair
    identity = verifier_for(settings, keypair).verify(
        make_token(private, preferred_username="Wang@FuDao.Example"))
    assert identity.email == "wang@fudao.example"


# ── 偽造與竄改 ───────────────────────────────────────────────────────────────


def test_alg_none_is_refused(settings, keypair):
    """A header saying `none` means the token carries no signature at all."""
    now = int(time.time())
    unsigned = jwt.encode(
        {"iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT,
         "tid": TENANT, "oid": OID, "sub": "s", "iat": now, "exp": now + 3600},
        key="", algorithm="none", headers={"kid": KID})
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(unsigned)


def test_hmac_signed_with_the_public_key_is_refused(settings, keypair):
    """RS256→HS256 confusion: the signing key is published, so if HMAC were
    accepted, anyone could mint tokens with it.

    Assembled by hand because PyJWT refuses to *encode* this — it detects RSA
    key material being passed as an HMAC secret and raises. An attacker has no
    such scruples, so the forgery is built byte by byte and the verifier is
    asked about it directly.
    """
    import base64
    import hashlib
    import hmac as hmaclib

    from cryptography.hazmat.primitives import serialization

    _, public = keypair
    pem = public.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo)

    def segment(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode().rstrip("=")

    now = int(time.time())
    header = segment(json.dumps({"alg": "HS256", "typ": "JWT", "kid": KID}).encode())
    payload = segment(json.dumps({
        "iss": f"https://login.microsoftonline.com/{TENANT}/v2.0", "aud": CLIENT,
        "tid": TENANT, "oid": OID, "sub": "s", "iat": now, "exp": now + 3600,
    }).encode())
    signature = segment(
        hmaclib.new(pem, f"{header}.{payload}".encode(), hashlib.sha256).digest())

    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(f"{header}.{payload}.{signature}")


def test_signature_from_another_key_is_refused(settings, keypair):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(make_token(other))


def test_tampered_payload_is_refused(settings, keypair):
    private, _ = keypair
    header, payload, signature = make_token(private).split(".")
    import base64
    raw = json.loads(base64.urlsafe_b64decode(payload + "=="))
    raw["oid"] = "attacker"
    swapped = base64.urlsafe_b64encode(
        json.dumps(raw).encode()).decode().rstrip("=")
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(f"{header}.{swapped}.{signature}")


# ── 對象與租戶 ───────────────────────────────────────────────────────────────


def test_token_for_another_app_is_refused(settings, keypair):
    """Any app registered in the same tenant can get a correctly-signed token
    for its own audience; without the aud check one of those would be enough."""
    private, _ = keypair
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(
            make_token(private, aud="some-other-app"))


def test_token_from_another_organisation_is_refused(settings, keypair):
    private, _ = keypair
    other = "00000000-0000-0000-0000-000000000000"
    with pytest.raises((WrongTenant, InvalidToken)):
        verifier_for(settings, keypair).verify(
            make_token(private, tid=other,
                       iss=f"https://login.microsoftonline.com/{other}/v2.0"))


def test_right_issuer_but_wrong_tid_is_refused(settings, keypair):
    """Belt and braces: iss already pins the tenant, but tid is checked too."""
    private, _ = keypair
    with pytest.raises(WrongTenant):
        verifier_for(settings, keypair).verify(
            make_token(private, tid="00000000-0000-0000-0000-000000000000"))


# ── 時間與必要宣告 ───────────────────────────────────────────────────────────


def test_expired_token_is_refused(settings, keypair):
    private, _ = keypair
    now = int(time.time())
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(
            make_token(private, iat=now - 7200, nbf=now - 7200, exp=now - 3600))


def test_not_yet_valid_token_is_refused(settings, keypair):
    private, _ = keypair
    now = int(time.time())
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(
            make_token(private, nbf=now + 3600, exp=now + 7200))


def test_token_without_oid_is_refused(settings, keypair):
    """Without a stable subject there is nothing to key an account on, and
    falling back to email would key it on something that changes."""
    private, _ = keypair
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair).verify(make_token(private, oid=None))


def test_unconfigured_service_refuses_before_looking_at_the_token(keypair):
    private, _ = keypair
    blank = Settings(microsoft_tenant_id="", microsoft_client_id="")
    with pytest.raises(NotConfigured):
        verifier_for(blank, keypair).verify(make_token(private))


def test_unknown_key_is_refused_not_crashed(settings, keypair):
    private, _ = keypair
    with pytest.raises(InvalidToken):
        verifier_for(settings, keypair, fail=True).verify(make_token(private))


# ── 端點行為 ─────────────────────────────────────────────────────────────────


@pytest.fixture
def signed_in(client, keypair, monkeypatch):
    """Points the endpoint's verifier at the test key pair."""
    from app import routers
    _, public = keypair

    original = routers.auth.TokenVerifier

    def patched(settings, keys=None):
        return original(settings, keys=StubKeyStore(public))

    monkeypatch.setattr(routers.auth, "TokenVerifier", patched)

    from app.config import get_settings
    from app.main import app as fastapi_app
    fastapi_app.dependency_overrides[get_settings] = lambda: Settings(
        microsoft_tenant_id=TENANT, microsoft_client_id=CLIENT,
        microsoft_auto_provision=False)
    yield client
    fastapi_app.dependency_overrides.pop(get_settings, None)


def post_token(client, private, **overrides):
    return client.post("/api/v1/auth/microsoft",
                       json={"id_token": make_token(private, **overrides),
                             "device_name": "王老師的 iPad"})


def test_directory_membership_alone_does_not_grant_access(signed_in, keypair):
    """The tenant holds more than teachers. Being in it is not a credential."""
    private, _ = keypair
    response = post_token(signed_in, private)
    assert response.status_code == 403
    assert "老師帳號" in response.json()["detail"]


def test_pre_created_teacher_is_claimed_by_email_on_first_sign_in(signed_in, keypair):
    private, _ = keypair
    with SessionLocal() as db:
        db.add(Teacher(name="待認領", email="wang@fudao.example"))
        db.commit()

    response = post_token(signed_in, private)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["teacher_name"] == "王老師"      # directory wins on the name
    assert body["expires_at"] is not None       # and the token expires

    with SessionLocal() as db:
        teacher = db.query(Teacher).one()
        assert teacher.microsoft_oid == OID
        assert db.query(ApiToken).count() == 1


def test_second_sign_in_reuses_the_teacher_and_issues_a_new_device_token(
        signed_in, keypair):
    private, _ = keypair
    with SessionLocal() as db:
        db.add(Teacher(name="待認領", email="wang@fudao.example"))
        db.commit()

    assert post_token(signed_in, private).status_code == 200
    assert post_token(signed_in, private).status_code == 200

    with SessionLocal() as db:
        assert db.query(Teacher).count() == 1
        assert db.query(ApiToken).count() == 2


def test_renamed_account_keeps_its_history(signed_in, keypair):
    """Identity is keyed on oid, so a changed address is not a new person."""
    private, _ = keypair
    with SessionLocal() as db:
        db.add(Teacher(name="王老師", email="wang@fudao.example",
                       microsoft_oid=OID))
        db.commit()

    response = post_token(signed_in, private,
                          preferred_username="wang.new@fudao.example")
    assert response.status_code == 200
    with SessionLocal() as db:
        teacher = db.query(Teacher).one()
        assert teacher.email == "wang.new@fudao.example"


def test_disabled_teacher_cannot_sign_in(signed_in, keypair):
    from datetime import UTC, datetime
    private, _ = keypair
    with SessionLocal() as db:
        db.add(Teacher(name="離職", email="wang@fudao.example",
                       microsoft_oid=OID, disabled_at=datetime.now(UTC)))
        db.commit()

    assert post_token(signed_in, private).status_code == 403


def test_issued_token_actually_works(signed_in, keypair):
    private, _ = keypair
    with SessionLocal() as db:
        db.add(Teacher(name="待認領", email="wang@fudao.example"))
        db.commit()

    token = post_token(signed_in, private).json()["token"]
    me = signed_in.get("/api/v1/auth/me",
                       headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["name"] == "王老師"
