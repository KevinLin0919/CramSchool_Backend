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
os.environ["COMPAT_REQUIRE_AUTH"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from PIL import Image as PILImage  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Base, InviteCode, Teacher  # noqa: E402
from app.security import generate_token, hash_token  # noqa: E402


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
