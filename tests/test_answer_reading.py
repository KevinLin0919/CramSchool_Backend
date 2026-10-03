import base64
import json
from functools import partial

import httpx
import pytest

from app import answer_reading
from app.config import get_settings
from app.routers import templates


@pytest.fixture
def vision(monkeypatch):
    monkeypatch.setattr(get_settings(), "google_vision_api_key", "test-key")
    calls: list[dict] = []

    def install(reply):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            calls.append({"key": request.url.params.get("key"), "count": len(body["requests"])})
            return reply(body)

        monkeypatch.setattr(
            templates, "read_answers",
            partial(answer_reading.read_answers, transport=httpx.MockTransport(handler)),
        )

    install.calls = calls
    return install


def _page(make_png) -> str:
    return base64.b64encode(make_png()).decode()


def test_read_answers_disabled(client, manager_auth, monkeypatch):
    monkeypatch.setattr(get_settings(), "google_vision_api_key", None)
    res = client.post("/api/v1/templates/read-answers",
                      json={"image_base64": "", "boxes": []}, headers=manager_auth)
    assert res.status_code == 503
    assert res.json()["detail"] == "正解辨識尚未啟用"


def test_read_answers_requires_login(client):
    res = client.post("/api/v1/templates/read-answers", json={"image_base64": "", "boxes": []})
    assert res.status_code == 401


def test_read_answers_in_order_and_batched(client, manager_auth, make_png, vision):
    # 20 cells → two requests to Google (16 + 4), answers back in cell order.
    def reply(body):
        return httpx.Response(200, json={"responses": [
            {"fullTextAnnotation": {"text": f" {n}\n"}} for n in range(len(body["requests"]))
        ]})

    vision(reply)
    boxes = [[i, 0, i + 1, 1] for i in range(20)]
    res = client.post("/api/v1/templates/read-answers",
                      json={"image_base64": _page(make_png), "boxes": boxes}, headers=manager_auth)
    assert res.status_code == 200
    texts = [r["text"] for r in res.json()["results"]]
    assert texts == [str(n) for n in range(16)] + [str(n) for n in range(4)]
    assert [c["count"] for c in vision.calls] == [16, 4]
    assert all(c["key"] == "test-key" for c in vision.calls)


def test_read_answers_skips_empty_cells_and_hides_errors(client, manager_auth, make_png, vision):
    def reply(body):
        return httpx.Response(200, json={"responses": [
            {"error": {"message": "internal detail"}},
            {"fullTextAnnotation": {"text": "B"}},
        ]})

    vision(reply)
    # The middle box lies off the page and is never sent.
    boxes = [[0, 0, 1, 1], [5000, 5000, 5001, 5001], [1, 1, 2, 2]]
    res = client.post("/api/v1/templates/read-answers",
                      json={"image_base64": _page(make_png), "boxes": boxes}, headers=manager_auth)
    assert res.status_code == 200
    assert [r["text"] for r in res.json()["results"]] == ["", "", "B"]
    assert [c["count"] for c in vision.calls] == [2]


def test_read_answers_upstream_failure(client, manager_auth, make_png, vision):
    vision(lambda body: httpx.Response(500))
    res = client.post("/api/v1/templates/read-answers",
                      json={"image_base64": _page(make_png), "boxes": [[0, 0, 1, 1]]},
                      headers=manager_auth)
    assert res.status_code == 502


def test_read_answers_rejects_bad_image(client, manager_auth, vision):
    vision(lambda body: httpx.Response(200, json={"responses": []}))
    body = {"image_base64": "bm90IGFuIGltYWdl", "boxes": [[0, 0, 1, 1]]}
    res = client.post("/api/v1/templates/read-answers", json=body, headers=manager_auth)
    assert res.status_code == 400
