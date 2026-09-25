"""Test harness.

Environment is set before any app module is imported, because `app.db` builds
its engine at import time. Each run gets a throwaway directory so blobs from
one run can never satisfy another's assertions.
"""

import io
import os
import tempfile
from pathlib import Path

_TMP = Path(tempfile.mkdtemp(prefix="cramschool-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP / 'test.db'}"
os.environ["DATA_DIR"] = str(_TMP / "data")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, InviteCode, Teacher  # noqa: E402
from app.security import generate_token, hash_token  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_rate_limits():
    """Every test starts with the counters at zero.

    The suite enrols dozens of devices from one address, which is exactly the
    shape the limiter exists to refuse. Without this the limit is real and the
    tests are wrong; with it, the limit is still real and gets its own test
    below rather than being discovered as everybody else's failure.
    """
    from app.routers.auth import _auth_limit, _web_limit

    _auth_limit.reset()
    _web_limit.reset()
    yield
    _auth_limit.reset()
    _web_limit.reset()


@pytest.fixture(autouse=True)
def fresh_database():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield
    Base.metadata.drop_all(engine)


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def _enrol(client: TestClient, name: str, role: str) -> str:
    with SessionLocal() as db:
        teacher = Teacher(name=name, role=role)
        db.add(teacher)
        db.flush()
        code = generate_token()
        db.add(InviteCode(code_hash=hash_token(code), teacher_id=teacher.id))
        db.commit()

    response = client.post("/api/v1/auth/token", json={"invite_code": code})
    assert response.status_code == 200, response.text
    return response.json()["token"]


@pytest.fixture
def auth(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_enrol(client, '王老師', 'teacher')}"}


@pytest.fixture
def admin_auth(client) -> dict[str, str]:
    """Someone who may edit the shared answer keys.

    Kept separate from `auth` rather than making every test account an admin,
    because the interesting assertion is what an ordinary teacher CANNOT do —
    and a suite where everyone is an admin cannot make it.
    """
    return {"Authorization": f"Bearer {_enrol(client, '林主任', 'admin')}"}


@pytest.fixture
def other_auth(client) -> dict[str, str]:
    """A second teacher at the same school, for anything about isolation.

    Grading records are scoped to whoever produced them, and a scoping rule
    with only one subject in the suite is a rule nothing can fail against.
    """
    return {"Authorization": f"Bearer {_enrol(client, '陳老師', 'teacher')}"}


@pytest.fixture
def make_png():
    """Distinct images per call, so dedup tests are testing dedup."""

    def _make(width: int = 800, height: int = 1000, colour: tuple = (240, 240, 235)) -> bytes:
        buffer = io.BytesIO()
        PILImage.new("RGB", (width, height), colour).save(buffer, format="PNG")
        return buffer.getvalue()

    return _make


@pytest.fixture
def uploaded_image(client, auth, make_png):
    def _upload(width: int = 800, height: int = 1000, colour: tuple = (240, 240, 235)) -> dict:
        response = client.post(
            "/api/v1/images",
            files={"file": ("master.png", make_png(width, height, colour), "image/png")},
            headers=auth,
        )
        assert response.status_code == 201, response.text
        return response.json()

    return _upload


@pytest.fixture(autouse=True)
def no_real_ai(monkeypatch):
    """No test may reach a real model: any HTTP from the AI layer fails loudly."""
    import httpx

    def refuse(self, *args, **kwargs):
        raise AssertionError("a test tried to call the real AI service")

    # The real network transport only: the test client and MockTransport
    # bring transports of their own and keep working.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", refuse)
