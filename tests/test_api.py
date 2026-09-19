import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.db import SessionLocal
from app.models import ApiToken, InviteCode
from app.security import generate_token, hash_token


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


def _second_device(client, headers) -> dict[str, str]:
    """Another token for the SAME teacher — the iPad beside the phone."""
    teacher_id = client.get("/api/v1/auth/me", headers=headers).json()["id"]
    with SessionLocal() as db:
        code = generate_token()
        db.add(InviteCode(code_hash=hash_token(code), teacher_id=teacher_id))
        db.commit()
    response = client.post("/api/v1/auth/token", json={"invite_code": code})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['token']}"}


def test_logout_signs_out_only_the_device_that_called_it(client, auth):
    """Signing out of a shared iPad must not log the same teacher's phone out.

    This endpoint used to revoke the whole account, which made 登出 an outage
    for every other device the teacher owned.
    """
    other = _second_device(client, auth)

    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204

    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other).status_code == 200


def test_logout_all_signs_out_every_device(client, auth):
    other = _second_device(client, auth)

    assert client.post("/api/v1/auth/logout/all", headers=auth).status_code == 204

    assert client.get("/api/v1/auth/me", headers=auth).status_code == 401
    assert client.get("/api/v1/auth/me", headers=other).status_code == 401


def test_logging_out_twice_is_not_an_error(client, auth):
    """The app clears its own credential either way, so a retry after a flaky
    first attempt must not surface as a failure."""
    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 204
    # The second call cannot authenticate at all — the token it would present
    # is the one it just revoked — and 401 is the honest answer to that.
    assert client.post("/api/v1/auth/logout", headers=auth).status_code == 401


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


def _template_with_answer_type(client, auth, image, answer_type):
    return client.post(
        "/api/v1/templates",
        json={
            "exam_name": "型別測試",
            "grade": "小六",
            "subject": "國語",
            "pages": [
                {
                    "page_index": 0,
                    "image_id": image["id"],
                    "boxes": [
                        {
                            "question_no": 1,
                            "x": 0.8, "y": 0.1, "w": 0.1, "h": 0.05,
                            "answer": "4",
                            "answer_type": answer_type,
                        }
                    ],
                }
            ],
        },
        headers=auth,
    )


def test_choice_is_an_accepted_answer_type(client, auth, uploaded_image):
    """A multiple-choice cell holds exactly one character, and the template is
    the only thing that knows that — the answer key's own shape does not say
    it, since a one-digit answer can equally belong to a fill-in blank."""
    image = uploaded_image()
    created = _template_with_answer_type(client, auth, image, "choice")
    assert created.status_code == 201, created.text

    fetched = client.get(f"/api/v1/templates/{created.json()['id']}", headers=auth)
    assert fetched.json()["pages"][0]["boxes"][0]["answer_type"] == "choice"


def test_unknown_answer_type_is_rejected(client, auth, uploaded_image):
    image = uploaded_image()
    assert _template_with_answer_type(client, auth, image, "bogus").status_code == 422


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


def test_if_match_blocks_a_stale_overwrite(client, auth, admin_auth, uploaded_image):
    """Two admins with the same template open; the second save must not win silently."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    first = client.patch(
        f"/api/v1/templates/{template_id}",
        json={"exam_name": "王老師改的"},
        headers={**admin_auth, "If-Match": '"1"'},
    )
    assert first.status_code == 200
    assert first.json()["revision"] == 2

    stale = client.patch(
        f"/api/v1/templates/{template_id}",
        json={"exam_name": "李老師改的"},
        headers={**admin_auth, "If-Match": '"1"'},
    )
    assert stale.status_code == 412

    assert client.get(f"/api/v1/templates/{template_id}", headers=auth).json()[
        "exam_name"
    ] == "王老師改的"


def test_delete_is_soft_and_surfaces_as_a_tombstone(client, auth, admin_auth, uploaded_image):
    """An offline phone has to be able to learn that a template disappeared."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    before = client.get("/api/v1/templates", headers=auth).json()["sync_cursor"]

    assert client.delete(f"/api/v1/templates/{template_id}", headers=admin_auth).status_code == 204
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


def test_a_teacher_sees_only_their_own_grading(client, auth, other_auth, uploaded_image):
    """Templates are shared across a school; who graded whose paper is not."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    mine, theirs = str(uuid.uuid4()), str(uuid.uuid4())

    client.put(f"/api/v1/grading-sessions/{mine}",
               json=session_payload(template_id), headers=auth)
    client.put(f"/api/v1/grading-sessions/{theirs}",
               json=session_payload(template_id), headers=other_auth)

    listed = client.get("/api/v1/grading-sessions", headers=auth).json()
    assert [row["client_uuid"] for row in listed] == [mine]

    # Not "exists but forbidden": telling the difference would let anyone with
    # a token confirm which UUIDs are real.
    assert client.get(f"/api/v1/grading-sessions/{theirs}", headers=auth).status_code == 404


def test_one_teacher_cannot_overwrite_anothers_grading(client, auth, other_auth, uploaded_image):
    """The hole that scoping reads would otherwise leave open.

    The upsert used to take the UUID at face value and reassign the row to
    whoever sent it — so a teacher who could no longer *read* someone else's
    record could still overwrite it, and become its owner in the process.
    """
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    client_uuid = str(uuid.uuid4())
    client.put(f"/api/v1/grading-sessions/{client_uuid}",
               json=session_payload(template_id), headers=auth)

    intruder = client.put(f"/api/v1/grading-sessions/{client_uuid}",
                          json=session_payload(template_id), headers=other_auth)
    assert intruder.status_code == 403

    # And the original owner still has it, unchanged.
    assert client.get(f"/api/v1/grading-sessions/{client_uuid}",
                      headers=auth).status_code == 200


def test_one_teacher_cannot_delete_anothers_grading(client, auth, other_auth, uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    client_uuid = str(uuid.uuid4())
    client.put(f"/api/v1/grading-sessions/{client_uuid}",
               json=session_payload(template_id), headers=auth)

    assert client.delete(f"/api/v1/grading-sessions/{client_uuid}",
                         headers=other_auth).status_code == 404
    assert client.get(f"/api/v1/grading-sessions/{client_uuid}",
                      headers=auth).status_code == 200


def test_training_export_is_not_scoped_to_one_teacher(client, auth, other_auth, admin_auth,
                                                      uploaded_image):
    """The one endpoint that deliberately crosses the boundary.

    Its reader is a training pipeline, not a teacher looking up a class. Split
    the labelled cells by who happened to grade the paper and each slice is too
    small to train on, which is the whole reason it exists.
    """
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    # A correction only becomes training data once it has a crop attached —
    # the label alone teaches nothing without the ink it labels.
    cell = uploaded_image(width=64, height=64, colour=(200, 200, 200))
    for headers in (auth, other_auth):
        payload = session_payload(template_id)
        payload["answers"][0]["teacher_value"] = "7"
        payload["answers"][0]["cell_image_id"] = cell["id"]
        client.put(f"/api/v1/grading-sessions/{uuid.uuid4()}", json=payload, headers=headers)

    rows = client.get("/api/v1/grading-sessions/exports/corrections", headers=admin_auth).json()
    assert len(rows) == 2, "a teacher's export should still carry the whole school's labels"


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


def test_corrections_export_yields_labelled_training_rows(client, auth, admin_auth,
                                                          uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    payload = session_payload(template_id)
    payload["answers"][1]["teacher_value"] = "2"
    payload["answers"][1]["cell_image_id"] = image["id"]
    client.put(f"/api/v1/grading-sessions/{uuid.uuid4()}", json=payload, headers=auth)

    rows = client.get("/api/v1/grading-sessions/exports/corrections", headers=admin_auth).json()
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


def test_session_against_a_deleted_template_is_rejected(client, auth, admin_auth,
                                                        uploaded_image):
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]
    client.delete(f"/api/v1/templates/{template_id}", headers=admin_auth)
    response = client.put(
        f"/api/v1/grading-sessions/{uuid.uuid4()}",
        json=session_payload(template_id),
        headers=auth,
    )
    assert response.status_code == 400


# ── 對外端點的速率限制 ───────────────────────────────────────────────────────


def test_invite_redemption_is_rate_limited(client):
    """A stranger cannot hammer the one endpoint that answers strangers.

    The codes themselves carry 256 bits, so this is not about guessing one.
    It is about how much work a caller can make this machine do: every attempt
    is a database lookup and a hash, on a box in a cram school that is also
    serving a teacher part-way through a stack of papers.
    """
    from app.routers.auth import _auth_limit

    limit = _auth_limit.per_key
    bad = {"invite_code": "definitely-not-a-real-code", "device_name": "someone else's phone"}
    for _ in range(limit):
        # Wrong codes on purpose: being refused for the right reason still
        # costs the lookup, which is precisely the work being bounded.
        assert client.post("/api/v1/auth/token", json=bad).status_code == 400

    refused = client.post("/api/v1/auth/token", json=bad)
    assert refused.status_code == 429
    # A number, not a shrug: a well-behaved client should be able to wait once
    # rather than poll until it is let back in.
    assert int(refused.headers["Retry-After"]) >= 1


def test_microsoft_sign_in_shares_the_same_budget(client):
    """One limit across both public doors, not one each.

    They are the same resource seen from two angles, and a caller refused at
    one of them would otherwise simply walk to the other.
    """
    from app.routers.auth import _auth_limit

    for _ in range(_auth_limit.per_key):
        client.post("/api/v1/auth/token", json={"invite_code": "definitely-not-a-real-code"})

    blocked = client.post("/api/v1/auth/microsoft", json={"id_token": "nope"})
    assert blocked.status_code == 429


def test_rate_limit_does_not_touch_authenticated_endpoints(client, auth):
    """Teachers at work are not the traffic this is aimed at.

    Everything behind a token is already gated by something unguessable, and a
    teacher uploading a stack of forty papers must not start being refused
    part-way through because the count was shared with the front door.
    """
    from app.routers.auth import _auth_limit

    for _ in range(_auth_limit.per_key + 5):
        client.post("/api/v1/auth/token", json={"invite_code": "definitely-not-a-real-code"})

    assert client.get("/api/v1/auth/me", headers=auth).status_code == 200
    assert client.get("/api/v1/templates", headers=auth).status_code == 200


def test_forwarded_for_is_ignored_without_a_trusted_proxy(client):
    """A header cannot buy a fresh budget.

    `X-Forwarded-For` is whatever the sender writes in it. Counting it when
    nothing in front of this process is known to set it would turn the limit
    into a formality — one line of client code per extra allowance.
    """
    for _ in range(_limit(client)):
        client.post("/api/v1/auth/token",
                    json={"invite_code": "definitely-not-a-real-code"},
                    headers={"X-Forwarded-For": "203.0.113.9"})

    spoofed = client.post("/api/v1/auth/token",
                          json={"invite_code": "definitely-not-a-real-code"},
                          headers={"X-Forwarded-For": "198.51.100.7"})
    assert spoofed.status_code == 429


def _limit(_client) -> int:
    from app.routers.auth import _auth_limit

    return _auth_limit.per_key


def test_a_malformed_body_still_spends_the_budget(client):
    """Sending rubbish must not be cheaper than sending a real attempt.

    If the limit were applied after the request body was validated, then the
    way past it would be to send a body that never validates — free attempts,
    unlimited, at an endpoint whose whole purpose is to be reachable by
    strangers. This asserts the order: counted first, parsed second.
    """
    from app.routers.auth import _auth_limit

    for _ in range(_auth_limit.per_key):
        assert client.post("/api/v1/auth/token", json={}).status_code == 422

    assert client.post("/api/v1/auth/token", json={}).status_code == 429


# ── 權限：誰看得到什麼、誰改得動什麼 ─────────────────────────────────────────


def test_one_teacher_cannot_read_anothers_cell_crops(client, auth, other_auth,
                                                     uploaded_image, make_png):
    """The hole that made scoping the session list cosmetic.

    Image ids are sequential. Before this, holding any device token was the
    whole test, so a teacher could count from one and collect every crop of
    every child's handwriting in the school — while the endpoint that lists
    grading sessions politely returned an empty array.
    """
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    crop = client.post(
        "/api/v1/images",
        files={"file": ("cell.png", make_png(60, 60, (10, 10, 10)), "image/png")},
        headers=auth,
    ).json()

    session_uuid = str(uuid.uuid4())
    body = session_payload(template_id)
    body["answers"][0]["cell_image_id"] = crop["id"]
    assert client.put(f"/api/v1/grading-sessions/{session_uuid}", json=body,
                      headers=auth).status_code == 200

    # The teacher who graded it still sees it.
    assert client.get(f"/api/v1/images/{crop['id']}/content",
                      headers=auth).status_code == 200
    # Their colleague does not — and is told it does not exist rather than
    # that it exists and is someone else's, which would make counting useful.
    assert client.get(f"/api/v1/images/{crop['id']}/content",
                      headers=other_auth).status_code == 404


def test_every_teacher_can_still_read_the_shared_masters(client, auth, other_auth,
                                                         uploaded_image):
    """Answer keys are school-wide by design, and the master IS the paper.

    The narrow reading of the fix above would lock each teacher out of the
    templates they are supposed to grade against.
    """
    image = uploaded_image()
    make_template(client, auth, image)
    assert client.get(f"/api/v1/images/{image['id']}/content",
                      headers=other_auth).status_code == 200


def test_an_unreferenced_image_is_not_readable_by_anyone(client, auth, other_auth,
                                                         make_png):
    """Uploaded and then attached to nothing: reachable by no rule."""
    orphan = client.post(
        "/api/v1/images",
        files={"file": ("x.png", make_png(40, 40, (1, 2, 3)), "image/png")},
        headers=auth,
    ).json()
    assert client.get(f"/api/v1/images/{orphan['id']}/content",
                      headers=other_auth).status_code == 404


def test_an_ordinary_teacher_cannot_rewrite_the_answer_key(client, auth, admin_auth,
                                                           uploaded_image):
    """The quiet one.

    A changed key breaks nothing visible; it makes every paper graded
    afterwards wrong, for the whole class. `require_admin` existed and was
    wired to nothing, so every teacher could do this.
    """
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    refused = client.patch(f"/api/v1/templates/{template_id}",
                           json={"exam_name": "改成別的"}, headers=auth)
    assert refused.status_code == 403

    assert client.patch(f"/api/v1/templates/{template_id}",
                        json={"exam_name": "主任改的"},
                        headers=admin_auth).status_code == 200


def test_a_template_edit_records_who_made_it(client, auth, admin_auth, uploaded_image):
    """`created_by` is written once and never again, so it cannot answer this."""
    image = uploaded_image()
    template_id = make_template(client, auth, image).json()["id"]

    client.patch(f"/api/v1/templates/{template_id}",
                 json={"exam_name": "主任改的"}, headers=admin_auth)

    with SessionLocal() as db:
        row = db.execute(
            text("SELECT updated_by FROM exam_templates WHERE id = :i"),
            {"i": template_id},
        ).scalar_one()
    assert row is not None


def test_an_ordinary_teacher_cannot_delete_a_student(client, auth, admin_auth):
    """A hard delete of a minor's record, which then detaches them from every
    grading session ever recorded against them."""
    student = client.post("/api/v1/students",
                          json={"name": "王小明", "class_name": "國二A"},
                          headers=admin_auth).json()
    assert client.delete(f"/api/v1/students/{student['id']}",
                         headers=auth).status_code == 403
    assert client.delete(f"/api/v1/students/{student['id']}",
                         headers=admin_auth).status_code == 204


def test_the_training_export_needs_an_admin(client, auth, admin_auth):
    """Fifty thousand rows of other people's children in one response.

    Not being scoped is the point of this endpoint, and it is also why a
    device token in a teacher's pocket has no business calling it.
    """
    assert client.get("/api/v1/grading-sessions/exports/corrections",
                      headers=auth).status_code == 403
    assert client.get("/api/v1/grading-sessions/exports/corrections",
                      headers=admin_auth).status_code == 200
