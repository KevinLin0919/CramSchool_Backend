import uuid
from datetime import UTC, datetime, timedelta

from app.db import SessionLocal
from app.models import ApiToken


def make_template(client, auth, image, *, name="高一數學・段考一", boxes=2):
    return client.post(
        "/api/v1/templates",
        json={
            "exam_name": name,
            "grade": "高一",
            "subject": "數學",
            "pages": [
                {
                    "page_index": 0,
                    "image_id": image["id"],
                    "boxes": [
                        {
                            "question_no": n,
                            "x": 0.8,
                            "y": 0.1 * n,
                            "w": 0.1,
                            "h": 0.05,
                            "answer": str(n),
                            "answer_type": "digit",
                        }
                        for n in range(1, boxes + 1)
                    ],
                }
            ],
        },
        headers=auth,
    )


# ── 認證 ─────────────────────────────────────────────────────────────────────


def test_endpoints_reject_anonymous_callers(client):
    assert client.get("/api/v1/templates").status_code == 401
    assert client.get("/api/v1/students").status_code == 401
    assert client.get("/api/v1/grading-sessions").status_code == 401


def test_health_needs_no_credential(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_invite_code_is_single_use(client):
    from app.models import InviteCode, Teacher
    from app.security import generate_token, hash_token

    with SessionLocal() as db:
        teacher = Teacher(name="李老師", role="teacher")
        db.add(teacher)
        db.flush()
        code = generate_token()
        db.add(InviteCode(code_hash=hash_token(code), teacher_id=teacher.id))
        db.commit()

    assert client.post("/api/v1/auth/token", json={"invite_code": code}).status_code == 200
    second = client.post("/api/v1/auth/token", json={"invite_code": code})
    assert second.status_code == 400
    assert "已被使用" in second.json()["detail"]


def test_revoked_token_stops_working(client, auth):
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200
    with SessionLocal() as db:
        for token in db.query(ApiToken).all():
            token.revoked_at = datetime.now(UTC)
        db.commit()
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401


def test_expired_token_stops_working(client, auth):
    with SessionLocal() as db:
        for token in db.query(ApiToken).all():
            token.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401


def test_raw_token_is_never_stored(client, auth):
    raw = auth["Authorization"].removeprefix("Bearer ")
    with SessionLocal() as db:
        stored = [t.token_hash for t in db.query(ApiToken).all()]
    assert raw not in stored


# ── 影像 ─────────────────────────────────────────────────────────────────────


def test_identical_uploads_deduplicate(client, auth, make_png):
    payload = make_png()
    first = client.post(
        "/api/v1/images", files={"file": ("a.png", payload, "image/png")}, headers=auth
    )
    second = client.post(
        "/api/v1/images", files={"file": ("b.png", payload, "image/png")}, headers=auth
    )
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["sha256"] == second.json()["sha256"]


def test_head_lets_a_client_skip_a_redundant_upload(client, auth, uploaded_image):
    image = uploaded_image()
    assert client.head(f"/api/v1/images/sha256/{image['sha256']}", headers=auth).status_code == 204
    assert client.head("/api/v1/images/sha256/" + "0" * 64, headers=auth).status_code == 404


def test_non_image_upload_is_rejected(client, auth):
    response = client.post(
        "/api/v1/images",
        files={"file": ("evil.png", b"definitely not a png", "image/png")},
        headers=auth,
    )
    assert response.status_code == 400


def test_image_dimensions_are_read_from_the_file(client, auth, uploaded_image):
    image = uploaded_image(width=1234, height=567)
    assert (image["width"], image["height"]) == (1234, 567)


# ── 模板 ─────────────────────────────────────────────────────────────────────


def test_create_and_read_template(client, auth, uploaded_image):
    image = uploaded_image()
    created = make_template(client, auth, image, boxes=3)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["annotation_count"] == 3
    assert body["revision"] == 1
    assert body["pages"][0]["image_width"] == 800

    fetched = client.get(f"/api/v1/templates/{body['id']}", headers=auth)
    assert fetched.status_code == 200
    assert fetched.headers["ETag"] == '"1"'
    assert [b["question_no"] for b in fetched.json()["pages"][0]["boxes"]] == [1, 2, 3]


def test_duplicate_question_numbers_are_rejected(client, auth, uploaded_image):
    image = uploaded_image()
    response = client.post(
        "/api/v1/templates",
        json={
            "exam_name": "重複題號",
            "pages": [
                {
                    "page_index": 0,
                    "image_id": image["id"],
                    "boxes": [
                        {"question_no": 1, "x": 0.1, "y": 0.1, "w": 0.1, "h": 0.1, "answer": "1"},
                        {"question_no": 1, "x": 0.2, "y": 0.2, "w": 0.1, "h": 0.1, "answer": "2"},
                    ],
                }
            ],
        },
        headers=auth,
    )
    assert response.status_code == 422


def test_referencing_a_missing_image_is_rejected(client, auth):
    response = client.post(
        "/api/v1/templates",
        json={
            "exam_name": "沒有圖",
            "pages": [{"page_index": 0, "image_id": 9999, "boxes": []}],
        },
        headers=auth,
    )
    assert response.status_code == 400
    assert "不存在" in response.json()["detail"]


def test_if_match_blocks_a_stale_overwrite(client, auth, uploaded_image):
    """Two teachers with the same template open; the second save must not win silently."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    first = client.patch(
        f"/api/v1/templates/{template_id}",
        json={"exam_name": "王老師改的"},
        headers={**auth, "If-Match": '"1"'},
    )
    assert first.status_code == 200
    assert first.json()["revision"] == 2

    stale = client.patch(
        f"/api/v1/templates/{template_id}",
        json={"exam_name": "李老師改的"},
        headers={**auth, "If-Match": '"1"'},
    )
    assert stale.status_code == 412

    assert client.get(f"/api/v1/templates/{template_id}", headers=auth).json()[
        "exam_name"
    ] == "王老師改的"


def test_delete_is_soft_and_surfaces_as_a_tombstone(client, auth, uploaded_image):
    """An offline phone has to be able to learn that a template disappeared."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    before = client.get("/api/v1/templates", headers=auth).json()["sync_cursor"]

    assert client.delete(f"/api/v1/templates/{template_id}", headers=auth).status_code == 204
    assert client.get(f"/api/v1/templates/{template_id}", headers=auth).status_code == 404

    listing = client.get("/api/v1/templates", headers=auth).json()
    assert listing["templates"] == []

    synced = client.get(
        "/api/v1/templates", params={"updated_since": before}, headers=auth
    ).json()
    assert [t["id"] for t in synced["templates"]] == [template_id]
    assert synced["templates"][0]["deleted_at"] is not None


def test_sync_cursor_only_returns_changes(client, auth, uploaded_image):
    image = uploaded_image()
    make_template(client, auth, image, name="第一份")
    cursor = client.get("/api/v1/templates", headers=auth).json()["sync_cursor"]

    quiet = client.get("/api/v1/templates", params={"updated_since": cursor}, headers=auth)
    assert quiet.json()["templates"] == []

    make_template(client, auth, image, name="第二份")
    after = client.get("/api/v1/templates", params={"updated_since": cursor}, headers=auth)
    assert [t["exam_name"] for t in after.json()["templates"]] == ["第二份"]


def test_master_image_widths_are_restricted(client, auth, uploaded_image):
    image = uploaded_image(width=2000, height=2600)
    template_id = make_template(client, auth, image).json()["id"]

    assert client.get(
        f"/api/v1/templates/{template_id}/master", params={"w": 1600}, headers=auth
    ).status_code == 200
    rejected = client.get(
        f"/api/v1/templates/{template_id}/master", params={"w": 1601}, headers=auth
    )
    assert rejected.status_code == 400


def test_grade_and_subject_are_real_filters(client, auth, uploaded_image):
    image = uploaded_image()
    make_template(client, auth, image, name="高一數學・段考一")
    assert len(client.get(
        "/api/v1/templates", params={"grade": "高一"}, headers=auth
    ).json()["templates"]) == 1
    assert client.get(
        "/api/v1/templates", params={"grade": "國三"}, headers=auth
    ).json()["templates"] == []


# ── 批改結果 ─────────────────────────────────────────────────────────────────


def session_payload(template_id, **overrides):
    payload = {
        "template_id": template_id,
        "scanned_at": datetime.now(UTC).isoformat(),
        "app_version": "1.0.0",
        "answers": [
            {"question_no": 1, "expected": "1", "recognized": "1", "verdict": "correct",
             "confidence": 0.98, "margin": 0.9},
            {"question_no": 2, "expected": "2", "recognized": "3", "verdict": "wrong",
             "confidence": 0.71, "margin": 0.3},
        ],
    }
    payload.update(overrides)
    return payload


def test_reuploading_a_session_updates_instead_of_duplicating(client, auth, uploaded_image):
    """The retry-after-dropped-Wi-Fi case. A duplicate here is a duplicate grade."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    client_uuid = str(uuid.uuid4())
    payload = session_payload(template_id)

    first = client.put(f"/api/v1/grading-sessions/{client_uuid}", json=payload, headers=auth)
    second = client.put(f"/api/v1/grading-sessions/{client_uuid}", json=payload, headers=auth)

    assert first.status_code == 200 and second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert len(client.get("/api/v1/grading-sessions", headers=auth).json()) == 1


def test_score_is_recomputed_not_trusted(client, auth, uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    body = client.put(
        f"/api/v1/grading-sessions/{uuid.uuid4()}",
        json=session_payload(template_id),
        headers=auth,
    ).json()
    assert (body["correct_count"], body["total_count"]) == (1, 2)


def test_teacher_correction_is_captured_with_a_timestamp(client, auth, uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    client_uuid = str(uuid.uuid4())

    client.put(
        f"/api/v1/grading-sessions/{client_uuid}",
        json=session_payload(template_id),
        headers=auth,
    )

    corrected = session_payload(template_id)
    corrected["answers"][1]["teacher_value"] = "2"
    corrected["answers"][1]["cell_image_id"] = image["id"]
    body = client.put(
        f"/api/v1/grading-sessions/{client_uuid}", json=corrected, headers=auth
    ).json()

    answer = next(a for a in body["answers"] if a["question_no"] == 2)
    assert answer["teacher_value"] == "2"
    assert answer["corrected_at"] is not None


def test_corrections_export_yields_labelled_training_rows(client, auth, uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    payload = session_payload(template_id)
    payload["answers"][1]["teacher_value"] = "2"
    payload["answers"][1]["cell_image_id"] = image["id"]
    client.put(f"/api/v1/grading-sessions/{uuid.uuid4()}", json=payload, headers=auth)

    rows = client.get("/api/v1/grading-sessions/exports/corrections", headers=auth).json()
    assert len(rows) == 1
    assert rows[0]["label"] == "2"
    assert rows[0]["model_read"] == "3"
    assert rows[0]["cell_image_url"].endswith("/content")


def test_invalid_verdict_is_rejected(client, auth, uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    payload = session_payload(template_id)
    payload["answers"][0]["verdict"] = "maybe"
    response = client.put(
        f"/api/v1/grading-sessions/{uuid.uuid4()}", json=payload, headers=auth
    )
    assert response.status_code == 422


def test_session_against_a_deleted_template_is_rejected(client, auth, uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    client.delete(f"/api/v1/templates/{template_id}", headers=auth)
    response = client.put(
        f"/api/v1/grading-sessions/{uuid.uuid4()}",
        json=session_payload(template_id),
        headers=auth,
    )
    assert response.status_code == 400
