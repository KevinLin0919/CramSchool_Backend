"""The numbers the reports and the AI quote."""

import uuid

from app.analytics import Item, Paper, exam_report, item_stats, paper_score
from app.db import SessionLocal
from app.grading import BLANK
from app.models import ExamTemplate, GradingSession, SchoolClass, Student
from app.simulate import purge, seed
from tests.test_classes_exams import _choice_template, _class, _upload

ITEMS = [Item(1, "choice", "2"), Item(2, "mark", "X"), Item(3, "choice", "4")]


def _paper(sid, answers):
    return Paper(session_id=sid, student_id=sid, answers=answers)


def test_the_denominator_is_the_paper_not_what_was_scanned():
    half_scanned = _paper(1, {1: ("2", "correct")})
    assert paper_score(half_scanned, ITEMS) == {
        "correct": 1, "total": 3, "pending": 2, "choice": [1, 2], "mark": [0, 1]}


def test_small_groups_get_counts_not_rates():
    papers = [_paper(i, {1: ("3", "wrong"), 2: ("X", "correct")}) for i in range(3)]
    report = exam_report(ITEMS, papers, 4)
    q1 = report["items"][0]
    assert report["small_group"] is True
    assert q1["correct_rate"] is None and q1["discrimination"] is None
    assert q1["options"] == {"1": 0, "2": 0, "3": 3, "4": 0}
    assert "unanimous_wrong" in q1["flags"]


def test_blank_and_pending_are_kept_apart():
    papers = [_paper(1, {1: (BLANK, "wrong")}), _paper(2, {1: (None, "unsure")}),
              _paper(3, {1: ("2", "correct")})]
    q1 = item_stats(ITEMS[0], papers, 4, None)
    assert (q1["answered"], q1["blank"], q1["pending"], q1["correct"]) == (2, 1, 1, 1)


def test_discrimination_and_the_popular_wrong_option_on_a_full_class():
    papers = []
    for i in range(20):
        strong = i < 10
        papers.append(_paper(i, {
            1: ("2", "correct") if strong else ("3", "wrong"),
            3: ("4", "correct") if i % 2 else ("4", "correct"),
        }))
    report = exam_report(ITEMS, papers, 4)
    q1 = report["items"][0]
    assert q1["discrimination"] > 0.9
    assert q1["correct_rate"] == 0.5
    assert q1["high_low"]["high"]["2"] == q1["high_low"]["high_n"]
    assert report["mean"] is not None and report["median"] is not None


def test_a_mark_question_below_chance_is_flagged():
    papers = [_paper(i, {2: ("O" if i < 8 else "X", "wrong" if i < 8 else "correct")})
              for i in range(12)]
    q2 = exam_report(ITEMS, papers, 4)["items"][1]
    assert "guessable" in q2["flags"] and "below_chance" in q2["flags"]


def _exam_with_papers(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    cls = _class(client, auth, students=("甲", "乙", "丙"))
    exam = client.put(f"/api/v1/exams/{uuid.uuid4()}", json={
        "class_id": cls["id"], "template_id": template["id"], "exam_date": "2026-09-25",
    }, headers=auth).json()
    picks = ["3", "3", "2"]
    for student, pick in zip(cls["students"], picks, strict=True):
        paper, _ = _upload(client, auth, template["id"], [
            {"question_no": 1, "expected": "②", "recognized": pick, "verdict": "wrong"},
        ])
        client.put(f"/api/v1/grading-sessions/{paper}/assignment", json={
            "exam_uuid": exam["client_uuid"], "student_id": student["id"]}, headers=auth)
    return template, cls, exam


def test_the_exam_report_endpoint(client, auth, other_auth, uploaded_image):
    _, _, exam = _exam_with_papers(client, auth, uploaded_image)
    report = client.get(f"/api/v1/exams/{exam['client_uuid']}/report", headers=auth).json()
    assert report["papers"] == 3 and report["identified"] == 3 and report["total"] == 2
    q1 = report["items"][0]
    assert q1["options"]["3"] == 2 and q1["correct"] == 1
    # Question 2 was never scanned on any paper.
    assert report["items"][1]["pending"] == 3
    assert {p["student_name"] for p in report["paper_list"]} == {"甲", "乙", "丙"}
    assert client.get(f"/api/v1/exams/{exam['client_uuid']}/report",
                      headers=other_auth).status_code == 404


def test_who_chose_what(client, auth, uploaded_image):
    _, _, exam = _exam_with_papers(client, auth, uploaded_image)
    out = client.get(f"/api/v1/exams/{exam['client_uuid']}/items/1/students",
                     headers=auth).json()
    assert {s["student_name"] for s in out["groups"]["3"]} == {"甲", "乙"}


def test_student_profile_and_class_trend(client, auth, other_auth, uploaded_image):
    _, cls, _ = _exam_with_papers(client, auth, uploaded_image)
    student = cls["students"][2]["id"]
    profile = client.get(f"/api/v1/students/{student}/profile", headers=auth).json()
    assert profile["results"][0]["correct"] == 1
    assert client.get(f"/api/v1/students/{student}/profile",
                      headers=other_auth).status_code == 404
    trend = client.get(f"/api/v1/classes/{cls['id']}/trend", headers=auth).json()
    assert trend["exams"][0]["papers"] == 3 and len(trend["students"]) == 3


def test_the_simulated_class_is_seeded_realistically_and_purged_whole(client, auth,
                                                                      uploaded_image):
    templates = [_choice_template(client, auth, uploaded_image(colour=(i, i, i)))
                 for i in range(3)]
    teacher_id = client.get("/api/v1/auth/me", headers=auth).json()["id"]
    with SessionLocal() as db:
        rows = [db.get(ExamTemplate, t["id"]) for t in templates]
        cls = seed(db, teacher_id, rows, size=28)
        class_id = cls.id

    exams = client.get("/api/v1/exams", headers=auth).json()
    assert len(exams) == 3 and all(e["is_simulated"] for e in exams)
    report = client.get(f"/api/v1/exams/{exams[1]['client_uuid']}/report", headers=auth).json()
    assert report["papers"] == 28 and not report["small_group"]
    trend = client.get(f"/api/v1/classes/{class_id}/trend", headers=auth).json()
    assert len(trend["exams"]) == 3

    with SessionLocal() as db:
        assert purge(db, teacher_id) == 1
        assert db.query(SchoolClass).count() == 0
        assert db.query(GradingSession).count() == 0
        assert db.query(Student).count() == 0


def test_overview_previous_unit_and_watch_list(client, auth, uploaded_image):
    templates = [_choice_template(client, auth, uploaded_image(colour=(i, i, i)))
                 for i in range(3)]
    teacher_id = client.get("/api/v1/auth/me", headers=auth).json()["id"]
    with SessionLocal() as db:
        seed(db, teacher_id, [db.get(ExamTemplate, t["id"]) for t in templates], size=28)
    exams = client.get("/api/v1/exams", headers=auth).json()
    latest = exams[0]["client_uuid"]
    report = client.get(f"/api/v1/exams/{latest}/report", headers=auth).json()
    assert report["previous"] is not None and 0 <= report["previous"]["mean_rate"] <= 1
    for w in report["watch"]:
        assert w["drop"] >= 0.15 and w["usual_rate"] > w["rate"]
    first = exams[-1]["client_uuid"]
    assert client.get(f"/api/v1/exams/{first}/report", headers=auth).json()["previous"] is None

    overview = client.get("/api/v1/overview", headers=auth).json()
    assert len(overview["recent"]) == 3 and overview["classes"][0]["students"] == 28
    assert len(overview["classes"][0]["trend"]) == 3
