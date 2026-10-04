"""Answer keys from PDFs, and one numbering across a paper's pages."""

import base64
import io

from PIL import Image

from app import pdf_pages


def _pdf(pages: int = 2, size=(1240, 1754)) -> bytes:
    images = [Image.new("RGB", size, (255 - 40 * i, 255, 255)) for i in range(pages)]
    out = io.BytesIO()
    images[0].save(out, "PDF", save_all=True, append_images=images[1:], resolution=150)
    return out.getvalue()


def _post_pdf(client, headers, data: bytes, name="key.pdf"):
    return client.post("/api/v1/templates/pdf-pages", headers=headers,
                       files={"file": (name, data, "application/pdf")})


def test_every_page_comes_back_as_an_image_the_editor_can_use(client, manager_auth):
    response = _post_pdf(client, manager_auth, _pdf(2))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["page_count"] == 2 and [p["page_no"] for p in body["pages"]] == [1, 2]
    first = body["pages"][0]
    image = Image.open(io.BytesIO(base64.b64decode(first["image_base64"])))
    assert image.format == "JPEG" and image.size == (first["width"], first["height"])
    assert max(image.size) == pdf_pages.LONG_SIDE


def test_a_landscape_page_stays_landscape(client, manager_auth):
    page = _post_pdf(client, manager_auth, _pdf(1, size=(1754, 1240))).json()["pages"][0]
    assert page["width"] > page["height"]


def test_only_a_template_manager_can_have_pdfs_rendered(client, auth):
    assert _post_pdf(client, auth, _pdf(1)).status_code == 403


def test_not_a_pdf_is_refused(client, manager_auth):
    response = _post_pdf(client, manager_auth, b"\x89PNG not really", name="key.png")
    assert response.status_code == 400


def test_a_broken_pdf_is_refused_with_a_reason(client, manager_auth):
    response = _post_pdf(client, manager_auth, b"%PDF-1.7\n garbage")
    assert response.status_code == 400 and "PDF" in response.json()["detail"]


def test_too_many_pages_are_refused_before_rendering(client, manager_auth, monkeypatch):
    monkeypatch.setattr(pdf_pages, "MAX_PAGES", 2)
    response = _post_pdf(client, manager_auth, _pdf(3, size=(60, 80)))
    assert response.status_code == 413


def _page(index: int, image_id: int, numbers: list[int]) -> dict:
    return {"page_index": index, "image_id": image_id, "boxes": [
        {"question_no": n, "x": 0.1, "y": 0.05 * n, "w": 0.05, "h": 0.03, "answer": "1",
         "answer_type": "choice"} for n in numbers]}


def test_question_numbers_run_across_the_whole_paper(client, manager_auth, uploaded_image):
    front, back = uploaded_image(colour=(1, 1, 1)), uploaded_image(colour=(2, 2, 2))
    ok = client.post("/api/v1/templates", headers=manager_auth, json={
        "exam_name": "正反面", "pages": [_page(0, front["id"], [1, 2]),
                                      _page(1, back["id"], [3, 4])]})
    assert ok.status_code == 201, ok.text
    assert [len(p["boxes"]) for p in ok.json()["pages"]] == [2, 2]

    restarted = client.post("/api/v1/templates", headers=manager_auth, json={
        "exam_name": "背面重新編號", "pages": [_page(0, front["id"], [1, 2]),
                                       _page(1, back["id"], [1, 2])]})
    assert restarted.status_code == 422
    assert "連續編號" in str(restarted.json()["detail"])

    edited = client.patch(f"/api/v1/templates/{ok.json()['id']}", headers=manager_auth, json={
        "pages": [_page(0, front["id"], [1, 2]), _page(1, back["id"], [2, 3])]})
    assert edited.status_code == 422
