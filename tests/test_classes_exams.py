"""Classes, sittings, matching papers to students, and the web sign-in."""

import uuid

from sqlalchemy import text

from app.db import SessionLocal
from tests.test_api import make_template


def _choice_template(client, auth, image):
    body = {
        "exam_name": "4上社會 1-2 家鄉地形", "grade": "四年級", "subject": "社會",
        "pages": [{"page_index": 0, "image_id": image["id"], "boxes": [
            {"question_no": 1, "x": .1, "y": .1, "w": .05, "h": .05, "answer": "②",
             "answer_type": "choice"},
            {"question_no": 2, "x": .1, "y": .2, "w": .05, "h": .05, "answer": "X",
             "answer_type": "mark"},
        ]}],
    }
    response = client.post("/api/v1/templates", json=body, headers=auth)
    assert response.status_code == 201, response.text
    return response.json()


def _class(client, auth, name="四年甲班", students=("陳宥廷", "林品妤")):
    cls = client.post("/api/v1/classes", json={"name": name}, headers=auth).json()
    for student in students:
        cls = client.post(f"/api/v1/classes/{cls['id']}/students", json={"name": student},
                          headers=auth).json()
    return cls


def _upload(client, auth, template_id, answers, session_uuid=None):
    session_uuid = session_uuid or str(uuid.uuid4())
    response = client.put(f"/api/v1/grading-sessions/{session_uuid}", json={
        "template_id": template_id, "scanned_at": "2026-09-25T00:30:00Z", "answers": answers,
    }, headers=auth)
    assert response.status_code == 200, response.text
    return session_uuid, response.json()


def test_classes_belong_to_their_teacher(client, auth, other_auth):
    cls = _class(client, auth)
    assert [s["name"] for s in cls["students"]] == ["陳宥廷", "林品妤"]
    assert client.get("/api/v1/classes", headers=other_auth).json() == []
    assert client.post(f"/api/v1/classes/{cls['id']}/students", json={"name": "x"},
                       headers=other_auth).status_code == 404


def test_the_student_list_is_the_teachers_own_roster(client, auth, other_auth):
    _class(client, auth)
    assert client.get("/api/v1/students", headers=other_auth).json() == []
    assert len(client.get("/api/v1/students", headers=auth).json()) == 2


def test_an_exam_is_idempotent_and_a_second_phone_is_told_the_first(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    cls = _class(client, auth)
    body = {"class_id": cls["id"], "template_id": template["id"], "exam_date": "2026-09-25"}
    first = str(uuid.uuid4())
    a = client.put(f"/api/v1/exams/{first}", json=body, headers=auth).json()
    b = client.put(f"/api/v1/exams/{first}", json=body, headers=auth).json()
    assert a["client_uuid"] == b["client_uuid"] == first
    other_phone = client.put(f"/api/v1/exams/{uuid.uuid4()}", json=body, headers=auth).json()
    assert other_phone["client_uuid"] == first
    retake = client.put(f"/api/v1/exams/{uuid.uuid4()}", json={**body, "sitting": 2},
                        headers=auth).json()
    assert retake["client_uuid"] != first


def test_answers_are_snapshotted_and_rejudged_on_the_server(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    _, out = _upload(client, auth, template["id"], [
        {"question_no": 1, "expected": "②", "recognized": "2", "verdict": "correct"},
        # The correction screen's ✕ against an X key: the app called it wrong.
        {"question_no": 2, "expected": "X", "recognized": "O", "verdict": "wrong",
         "teacher_value": "✕"},
    ])
    by_q = {a["question_no"]: a for a in out["answers"]}
    assert (by_q[1]["answer_type"], by_q[1]["chosen"]) == ("choice", "2")
    assert (by_q[2]["chosen"], by_q[2]["verdict"]) == ("X", "correct")
    assert out["correct_count"] == 2


def test_a_resent_upload_does_not_unmatch_the_student(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    cls = _class(client, auth)
    exam = client.put(f"/api/v1/exams/{uuid.uuid4()}", json={
        "class_id": cls["id"], "template_id": template["id"], "exam_date": "2026-09-25",
    }, headers=auth).json()
    answers = [{"question_no": 1, "expected": "2", "recognized": "2", "verdict": "correct"}]
    paper, _ = _upload(client, auth, template["id"], answers)

    student = cls["students"][1]["id"]
    assigned = client.put(f"/api/v1/grading-sessions/{paper}/assignment", json={
        "exam_uuid": exam["client_uuid"], "student_id": student, "identity_source": "suggested",
    }, headers=auth).json()
    assert assigned["student_id"] == student and assigned["identity_source"] == "suggested"

    # What every app out there does after a correction: resend without a student.
    _, again = _upload(client, auth, template["id"], answers, session_uuid=paper)
    assert again["student_id"] == student
    assert again["exam_uuid"] == exam["client_uuid"]


def test_a_paper_cannot_be_given_someone_elses_student(client, auth, other_auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    theirs = _class(client, other_auth, students=("別班的學生",))
    paper, _ = _upload(client, auth, template["id"], [])
    response = client.put(f"/api/v1/grading-sessions/{paper}/assignment",
                          json={"student_id": theirs["students"][0]["id"]}, headers=auth)
    assert response.status_code == 400


def test_a_paper_cannot_join_a_sitting_of_another_paper(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    other = make_template(client, auth, uploaded_image(colour=(1, 2, 3))).json()
    cls = _class(client, auth)
    exam = client.put(f"/api/v1/exams/{uuid.uuid4()}", json={
        "class_id": cls["id"], "template_id": other["id"], "exam_date": "2026-09-25",
    }, headers=auth).json()
    paper, _ = _upload(client, auth, template["id"], [])
    response = client.put(f"/api/v1/grading-sessions/{paper}/assignment",
                          json={"exam_uuid": exam["client_uuid"]}, headers=auth)
    assert response.status_code == 400


def test_an_edit_that_does_not_mention_the_name_box_keeps_it(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    box = {"page_index": 0, "x": .8, "y": .05, "w": .15, "h": .04}
    set_ = client.patch(f"/api/v1/templates/{template['id']}",
                        json={"name_box": box, "unit": "1-2"}, headers=auth).json()
    assert set_["name_box"]["x"] == .8 and set_["unit"] == "1-2"
    # The phone's editor rewrites every page and knows nothing of name boxes.
    pages = [{"page_index": 0, "image_id": template["pages"][0]["image_id"], "boxes": []}]
    kept = client.patch(f"/api/v1/templates/{template['id']}", json={"pages": pages},
                        headers=auth).json()
    assert kept["name_box"] == set_["name_box"]
    cleared = client.patch(f"/api/v1/templates/{template['id']}", json={"name_box": None},
                           headers=auth).json()
    assert cleared["name_box"] is None


def test_regrade_follows_a_fixed_key(client, auth, uploaded_image):
    template = _choice_template(client, auth, uploaded_image())
    cls = _class(client, auth)
    exam = client.put(f"/api/v1/exams/{uuid.uuid4()}", json={
        "class_id": cls["id"], "template_id": template["id"], "exam_date": "2026-09-25",
    }, headers=auth).json()
    paper, out = _upload(client, auth, template["id"], [
        {"question_no": 1, "expected": "②", "recognized": "3", "verdict": "wrong"},
        {"question_no": 2, "expected": "X", "recognized": "", "verdict": "unsure"},
    ])
    assert out["correct_count"] == 0
    client.put(f"/api/v1/grading-sessions/{paper}/assignment",
               json={"exam_uuid": exam["client_uuid"]}, headers=auth)

    pages = template["pages"]
    pages[0]["boxes"][0]["answer"] = "3"
    client.patch(f"/api/v1/templates/{template['id']}", json={"pages": pages}, headers=auth)
    client.post(f"/api/v1/exams/{exam['client_uuid']}/regrade", headers=auth)

    after = client.get(f"/api/v1/grading-sessions/{paper}", headers=auth).json()
    by_q = {a["question_no"]: a for a in after["answers"]}
    assert by_q[1]["verdict"] == "correct" and by_q[1]["expected"] == "3"
    assert by_q[2]["verdict"] == "unsure"
    assert after["correct_count"] == 1


def test_the_name_crop_is_readable_by_its_owner_only(client, auth, other_auth, uploaded_image,
                                                     make_png):
    template = _choice_template(client, auth, uploaded_image())
    crop = client.post("/api/v1/images",
                       files={"file": ("n.png", make_png(300, 80, (9, 9, 9)), "image/png")},
                       headers=auth).json()
    paper, _ = _upload(client, auth, template["id"], [])
    client.put(f"/api/v1/grading-sessions/{paper}/assignment",
               json={"name_image_id": crop["id"]}, headers=auth)
    assert client.get(f"/api/v1/images/{crop['id']}/content", headers=auth).status_code == 200
    assert client.get(f"/api/v1/images/{crop['id']}/content",
                      headers=other_auth).status_code == 404


def test_a_browser_signs_in_with_a_code_from_the_phone(client, auth):
    code = client.post("/api/v1/auth/web-code", headers=auth).json()["code"]
    signed_in = client.post("/api/v1/auth/web-login", json={"code": code})
    assert signed_in.status_code == 200
    web = {"Authorization": f"Bearer {signed_in.json()['token']}"}
    assert client.get("/api/v1/auth/me", headers=web).status_code == 200
    # One use.
    assert client.post("/api/v1/auth/web-login", json={"code": code}).status_code == 400
    # A browser cannot mint codes of its own.
    assert client.post("/api/v1/auth/web-code", headers=web).status_code == 403
    with SessionLocal() as db:
        kind = db.execute(text("SELECT kind FROM api_tokens ORDER BY id DESC LIMIT 1")).scalar()
    assert kind == "web"


def test_a_new_code_retires_the_last(client, auth):
    first = client.post("/api/v1/auth/web-code", headers=auth).json()["code"]
    client.post("/api/v1/auth/web-code", headers=auth)
    assert client.post("/api/v1/auth/web-login", json={"code": first}).status_code == 400


def test_guessing_codes_does_not_lock_out_phone_sign_in(client, auth):
    for _ in range(12):
        client.post("/api/v1/auth/web-login", json={"code": "000000"})
    assert client.post("/api/v1/auth/web-login", json={"code": "000000"}).status_code == 429
    refused = client.post("/api/v1/auth/token", json={"invite_code": "nope-nope"})
    assert refused.status_code == 400
