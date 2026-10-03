import base64
from functools import partial

import httpx
import pytest
from fastapi.testclient import TestClient

from app import detection
from app.config import get_settings
from app.main import create_app
from app.routers import templates


@pytest.fixture
def detection_upstream(monkeypatch):
    monkeypatch.setattr(get_settings(), "yolo_url", "http://yolo.test:8082")

    def install(handler):
        monkeypatch.setattr(
            templates, "detect_layout",
            partial(detection.detect_layout, transport=httpx.MockTransport(handler)),
        )

    return install


def test_detect_disabled(client, manager_auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "yolo_url", None)
    res = client.post("/api/v1/templates/detect", json={"image_base64": ""}, headers=manager_auth)
    assert res.status_code == 503
    assert res.json()["detail"] == "此環境未啟用版面偵測"


def test_detect_requires_login(client):
    res = client.post("/api/v1/templates/detect", json={"image_base64": ""})
    assert res.status_code == 401


def test_detect_only_returns_boxes(client, manager_auth, make_png, detection_upstream):
    encoded = base64.b64encode(make_png()).decode()

    def upstream(request):
        import json

        assert str(request.url) == "http://yolo.test:8082/predict"
        assert json.loads(request.content) == {"image_base64": encoded}
        assert request.extensions["timeout"]["read"] == 90
        return httpx.Response(200, json={
            "detections": [{"bbox": [10, 20, 30, 40], "confidence": 0.9, "class": "answer"}],
            "num_detections": 1,
        })

    detection_upstream(upstream)
    res = client.post("/api/v1/templates/detect", json={"image_base64": encoded},
                      headers=manager_auth)
    assert res.status_code == 200
    assert res.json() == {"detections": [{"bbox": [10, 20, 30, 40], "confidence": 0.9}]}


@pytest.mark.parametrize("body", [
    {}, {"detections": "invalid"},
    {"detections": [{"bbox": [1, 2, 3], "confidence": 0.9}]},
    {"detections": [{"bbox": [3, 2, 1, 4], "confidence": 0.9}]},
    {"detections": [{"bbox": [1, 2, 3, 4], "confidence": "high"}]},
])
def test_detect_invalid_upstream(client, manager_auth, detection_upstream, body):
    detection_upstream(lambda _: httpx.Response(200, json=body))
    res = client.post("/api/v1/templates/detect", json={"image_base64": ""}, headers=manager_auth)
    assert res.status_code == 502


def test_detect_upstream_failure_releases_slot(client, manager_auth, detection_upstream):
    detection_upstream(lambda _: httpx.Response(500))
    for _ in range(3):
        res = client.post("/api/v1/templates/detect", json={"image_base64": ""},
                          headers=manager_auth)
        assert res.status_code == 502


def test_detect_timeout(client, manager_auth, detection_upstream):
    def timeout(request):
        raise httpx.ReadTimeout("timeout", request=request)

    detection_upstream(timeout)
    assert client.post("/api/v1/templates/detect", json={"image_base64": ""},
                       headers=manager_auth).status_code == 502


def test_detect_too_large(client, manager_auth):
    res = client.post("/api/v1/templates/detect", headers=manager_auth,
                      json={"image_base64": "a" * (20 * 1024 * 1024 + 1)})
    assert res.status_code == 413


def test_detect_busy(client, manager_auth, detection_upstream, monkeypatch):
    class Busy:
        def acquire(self, timeout):
            assert timeout == 30
            return False

    monkeypatch.setattr(detection, "_slots", Busy())
    res = client.post("/api/v1/templates/detect", json={"image_base64": ""}, headers=manager_auth)
    assert res.status_code == 503
    assert res.json()["detail"] == "偵測忙碌中，請稍後再試"


def test_create_template_metadata(client, manager_auth, uploaded_image):
    image = uploaded_image()
    metadata = {"unit": "分數", "option_count": 5,
                "name_box": {"page_index": 0, "x": 0.1, "y": 0.1, "w": 0.2, "h": 0.05}}
    res = client.post("/api/v1/templates", headers=manager_auth, json={
        "exam_name": "網頁模板", **metadata,
        "pages": [{"page_index": 0, "image_id": image["id"], "boxes": []}],
    })
    assert res.status_code == 201, res.text
    fetched = client.get(f"/api/v1/templates/{res.json()['id']}", headers=manager_auth).json()
    for key, value in metadata.items():
        assert res.json()[key] == value
        assert fetched[key] == value


@pytest.mark.parametrize("web", [True, False])
def test_static_mount_and_headers(tmp_path, monkeypatch, web):
    dist = tmp_path / "web"
    dist.mkdir()
    (dist / "index.html").write_text("<html>web</html>")
    monkeypatch.setenv("WEB_DIST", str(dist) if web else str(tmp_path / "none"))
    get_settings.cache_clear()
    try:
        with TestClient(create_app()) as client:
            res = client.get("/web/")
            assert res.status_code == (200 if web else 404)
            if web:
                assert "connect-src 'self'" in res.headers["Content-Security-Policy"]
                assert res.headers["X-Frame-Options"] == "DENY"
                assert res.headers["Cache-Control"] == "no-cache"
            # The standalone editor is gone; the report carries it now.
            assert client.get("/label/").status_code == 404
            assert "Content-Security-Policy" not in client.get("/health").headers
    finally:
        get_settings.cache_clear()


def test_a_teacher_cannot_spend_the_template_building_services(client, auth):
    """Detection and answer reading only ever serve building a template."""
    assert client.post("/api/v1/templates/detect", json={"image_base64": ""},
                       headers=auth).status_code == 403
    assert client.post("/api/v1/templates/read-answers",
                       json={"image_base64": "", "boxes": []}, headers=auth).status_code == 403
