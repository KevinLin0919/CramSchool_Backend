"""The web editor's payload remains usable by the app and its grading pipeline."""


def test_web_template_round_trip(client, auth, make_png):
    code = client.post("/api/v1/auth/web-code", headers=auth)
    assert code.status_code == 200, code.text
    login = client.post("/api/v1/auth/web-login", json={"code": code.json()["code"]})
    assert login.status_code == 200, login.text
    web_auth = {"Authorization": f"Bearer {login.json()['token']}"}
    uploaded = client.post("/api/v1/images", headers=web_auth,
                           files={"file": ("blank.png", make_png(), "image/png")})
    assert uploaded.status_code == 201, uploaded.text
    payload = {
        "exam_name": "網頁建立的選擇題", "unit": "分數", "option_count": 5,
        "name_box": {"page_index": 0, "x": 0.1, "y": 0.05, "w": 0.3, "h": 0.08},
        "pages": [{"page_index": 0, "image_id": uploaded.json()["id"], "boxes": [{
            "question_no": 7, "x": 0.2, "y": 0.3, "w": 0.1, "h": 0.05,
            "answer": "5", "answer_type": "choice", "label": "選擇題答案區",
        }]}],
    }
    created = client.post("/api/v1/templates", headers=web_auth, json=payload)
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]
    fetched = client.get(f"/api/v1/templates/{template_id}", headers=web_auth)
    assert fetched.status_code == 200
    data = fetched.json()
    for key in ("exam_name", "unit", "option_count", "name_box"):
        assert data[key] == payload[key]
    assert data["pages"][0]["image_id"] == uploaded.json()["id"]
    assert data["pages"][0]["boxes"] == payload["pages"][0]["boxes"]

    # Omitted name_box survives a later edit; explicit null deletes it.
    updated = client.patch(f"/api/v1/templates/{template_id}",
                           headers={**web_auth, "If-Match": f'"{data["revision"]}"'},
                           json={"exam_name": "重新命名"})
    assert updated.status_code == 200
    assert updated.json()["name_box"] == payload["name_box"]
    revision = updated.json()["revision"]
    assert revision == data["revision"] + 1
    cleared = client.patch(f"/api/v1/templates/{template_id}",
                           headers={**web_auth, "If-Match": f'"{revision}"'},
                           json={"name_box": None})
    assert cleared.status_code == 200
    assert cleared.json()["name_box"] is None
