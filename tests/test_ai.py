"""AI plumbing, with a fake model: no network, no key, no cost."""

import json
import uuid

import httpx
import pytest

from app.ai import service
from app.ai.grounding import Facts, ground
from app.ai.provider import Provider, Reply, Tool, ToolCall
from app.config import get_settings
from app.db import SessionLocal
from app.models import ExamTemplate
from app.simulate import seed
from tests.test_classes_exams import _choice_template


def test_numbers_come_only_from_facts():
    facts = Facts()
    f = facts.add("第 21 題 選 4 的人數", 26)
    out = ground(f"第 21 題有 {{{f}}} 人選 4。另外大約 30 人答錯。"
                 "三位學生沒寫。單元 1-2 較弱。", facts)
    assert out[0].text == "第 21 題有 26 人選 4。" and out[0].verified
    assert not out[1].verified          # 30 was invented
    assert not out[2].verified          # 三位 is a count in words
    assert out[3].verified              # 1-2 names a unit


def test_an_unknown_fact_id_is_not_verified():
    out = ground("有 {F9} 人。", Facts())
    assert not out[0].verified


class FakeProvider:
    """Answers from a script and remembers every prompt it was shown."""

    prompts: list[str] = []
    script: list[Reply] = []

    def __init__(self, settings):
        self.settings = settings

    def complete(self, system, turns, tools=None, max_tokens=1200):
        FakeProvider.prompts.append(system + "\n" + "\n".join(
            json.dumps(t.get("result"), ensure_ascii=False) if t["role"] == "tool"
            else str(t.get("text", "")) for t in turns))
        return FakeProvider.script.pop(0)


@pytest.fixture
def ai_on(monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "opencode_api_key", "test-key")
    monkeypatch.setattr(settings, "ai_daily_budget_usd", 3.0)
    monkeypatch.setattr(service, "Provider", FakeProvider)
    FakeProvider.prompts = []
    FakeProvider.script = []
    return settings


def _simulated_exam(client, auth, uploaded_image):
    templates = [_choice_template(client, auth, uploaded_image(colour=(i, i, i))) for i in range(3)]
    teacher_id = client.get("/api/v1/auth/me", headers=auth).json()["id"]
    with SessionLocal() as db:
        seed(db, teacher_id, [db.get(ExamTemplate, t["id"]) for t in templates], size=12)
    return client.get("/api/v1/exams", headers=auth).json()[0]["client_uuid"]


def test_without_a_key_ai_says_so(client, auth, uploaded_image, monkeypatch):
    monkeypatch.setattr(get_settings(), "opencode_api_key", "")
    exam = _simulated_exam(client, auth, uploaded_image)
    response = client.post(f"/api/v1/ai/exams/{exam}/summary", headers=auth)
    assert response.status_code == 503


def test_explain_runs_in_the_background_and_grounds_numbers(client, auth, uploaded_image, ai_on):
    exam = _simulated_exam(client, auth, uploaded_image)
    FakeProvider.script = [Reply(json.dumps({
        "concept": "辨別地形", "why": "有 {F1} 人作答。其中 12 人被誤導。",
        "suggestion": "比較兩種地形。", "key_check": False}), input_tokens=1000, output_tokens=200)]
    run = client.post(f"/api/v1/ai/exams/{exam}/items/1/explain", headers=auth).json()
    done = client.get(f"/api/v1/ai/runs/{run['id']}", headers=auth).json()
    assert done["status"] == "done", done
    why = done["answer"]["why"]
    assert why[0]["verified"] and "{F1}" not in why[0]["text"]
    assert not why[1]["verified"]       # the 12 was the model's own
    assert done["cost_usd"] > 0

    # Same question, unchanged data: answered from the cache, not the model.
    again = client.post(f"/api/v1/ai/exams/{exam}/items/1/explain", headers=auth).json()
    assert again["id"] == run["id"] and FakeProvider.script == []


def test_student_names_never_reach_the_model(client, auth, uploaded_image, ai_on):
    exam = _simulated_exam(client, auth, uploaded_image)
    FakeProvider.script = [Reply(json.dumps({"summary": "S01 需要注意。", "focus": []}))]
    run = client.post(f"/api/v1/ai/exams/{exam}/summary", headers=auth).json()
    done = client.get(f"/api/v1/ai/runs/{run['id']}", headers=auth).json()
    report = client.get(f"/api/v1/exams/{exam}/report", headers=auth).json()
    names = {p["student_name"] for p in report["paper_list"]}
    assert not any(name in prompt for prompt in FakeProvider.prompts for name in names)
    # …but the teacher sees names, not codes.
    assert "S01" not in done["answer"]["summary"][0]["text"]


def test_free_questions_use_tools_then_answer(client, auth, uploaded_image, ai_on):
    exam = _simulated_exam(client, auth, uploaded_image)
    FakeProvider.script = [
        Reply("", tool_calls=[ToolCall("c1", "item_detail", {"question_no": 1})],
              raw_assistant=[]),
        Reply("第 1 題有 {F1} 人作答。"),
    ]
    run = client.post(f"/api/v1/ai/exams/{exam}/ask", json={"question": "第一題怎麼樣？"},
                      headers=auth).json()
    done = client.get(f"/api/v1/ai/runs/{run['id']}", headers=auth).json()
    assert done["status"] == "done", done
    assert done["answer"]["answer"][0]["verified"]


def test_the_daily_budget_stops_new_runs(client, auth, uploaded_image, ai_on, monkeypatch):
    exam = _simulated_exam(client, auth, uploaded_image)
    monkeypatch.setattr(ai_on, "ai_daily_budget_usd", 0.0)
    response = client.post(f"/api/v1/ai/exams/{exam}/summary", headers=auth)
    assert response.status_code == 429


def test_another_teacher_cannot_read_a_run(client, auth, other_auth, uploaded_image, ai_on):
    exam = _simulated_exam(client, auth, uploaded_image)
    FakeProvider.script = [Reply(json.dumps({"summary": "好。", "focus": []}))]
    run = client.post(f"/api/v1/ai/exams/{exam}/summary", headers=auth).json()
    assert client.get(f"/api/v1/ai/runs/{run['id']}", headers=other_auth).status_code == 404
    assert client.post(f"/api/v1/ai/exams/{exam}/summary",
                       headers=other_auth).status_code == 404


def _provider(style, handler):
    settings = get_settings().model_copy(update={
        "opencode_api_key": "k", "ai_api_style": style, "ai_model": "m"})
    return Provider(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_anthropic_wire_format():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        seen["auth"] = request.headers["authorization"]
        return httpx.Response(200, json={
            "content": [{"type": "text", "text": "好"},
                        {"type": "tool_use", "id": "t1", "name": "x", "input": {"a": 1}}],
            "usage": {"input_tokens": 5, "output_tokens": 2}})

    reply = _provider("anthropic", handler).complete(
        "sys", [{"role": "user", "text": "hi"}], tools=[Tool("x", "d", {"type": "object"})])
    assert seen["path"].endswith("/messages") and seen["auth"] == "Bearer k"
    assert seen["body"]["tools"][0]["input_schema"] == {"type": "object"}
    assert reply.text == "好" and reply.tool_calls[0].arguments == {"a": 1}


def test_openai_responses_wire_format():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={
            "output": [{"type": "function_call", "call_id": "c", "name": "x", "arguments": "{}"},
                       {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}],
            "usage": {"input_tokens": 3, "output_tokens": 1}})

    reply = _provider("openai", handler).complete("sys", [{"role": "user", "text": "hi"}],
                                                  tools=[Tool("x", "d", {"type": "object"})])
    assert seen["path"].endswith("/responses") and seen["body"]["instructions"] == "sys"
    assert reply.text == "ok" and reply.tool_calls[0].name == "x"


def test_question_strip_is_cut_from_the_master(client, auth, uploaded_image):
    from app.ai.imaging import question_strip
    from app.deps import get_store
    template = _choice_template(client, auth, uploaded_image())
    with SessionLocal() as db:
        row = service._load_template(db, template["id"])
        images = question_strip(row, 1, service._page_bytes(db, row))
    assert images is not None and images[0][:4] == b"\x89PNG"
    assert get_store() is not None
    assert uuid  # imported for fixtures above
