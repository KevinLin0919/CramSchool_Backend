"""Verification of the one-shot import from the Flask/SQLite service.

The legacy schema here is copied verbatim from `CramSchool_Storing/main.py`, so
these tests fail if the real thing turns out to differ from what was assumed.

What matters most is that boxes land in the same place. A migration that shifts
every answer cell by a few pixels produces templates that still look correct in
a list view and quietly mis-grade every paper scanned against them.
"""

import io
import json
import sqlite3

import pytest
from PIL import Image as PILImage

from app.coords import normalized_to_canvas
from app.db import SessionLocal
from app.models import AnswerBox, ExamTemplate

LEGACY_SCHEMA = """
    CREATE TABLE exam_templates (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_name  TEXT NOT NULL,
        image_path TEXT NOT NULL,
        pages      TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
"""


@pytest.fixture
def legacy(tmp_path):
    """Builds a stand-in for the deployed service's data directory."""
    uploads = tmp_path / "uploads" / "templates"
    uploads.mkdir(parents=True)
    db_path = tmp_path / "templates.db"

    def _build(rows: list[dict], image_size: tuple[int, int] = (800, 1000)) -> tuple:
        conn = sqlite3.connect(db_path)
        conn.execute(LEGACY_SCHEMA)
        for row in rows:
            buffer = io.BytesIO()
            PILImage.new("RGB", image_size, (250, 249, 246)).save(buffer, format="PNG")
            filename = f"template_{row['id']}.png"
            (uploads / filename).write_bytes(buffer.getvalue())
            conn.execute(
                "INSERT INTO exam_templates (id, exam_name, image_path, pages, created_at)"
                " VALUES (?,?,?,?,?)",
                (
                    row["id"],
                    row["exam_name"],
                    filename,
                    json.dumps(row["pages"], ensure_ascii=False),
                    row.get("created_at", "2026-03-16T14:59:00"),
                ),
            )
        conn.commit()
        conn.close()
        return db_path, uploads

    return _build


def run_import(monkeypatch, db_path, uploads, *, dry_run=False):
    import sys

    from scripts.import_legacy import main

    argv = ["import_legacy", "--legacy-db", str(db_path), "--legacy-uploads", str(uploads)]
    if dry_run:
        argv.append("--dry-run")
    monkeypatch.setattr(sys, "argv", argv)
    return main()


def test_boxes_land_in_the_same_place_after_migration(legacy, monkeypatch):
    original = [123.5, 88.25, 64.0, 40.5]
    db_path, uploads = legacy(
        [
            {
                "id": 1,
                "exam_name": "康軒二上國語第一回",
                "pages": [
                    {
                        "image": "page_1.png",
                        "annotations": [
                            {"class": "答案區", "bbox": original, "answer": "怪"}
                        ],
                    }
                ],
            }
        ]
    )

    assert run_import(monkeypatch, db_path, uploads) == 0

    with SessionLocal() as db:
        box = db.query(AnswerBox).one()
        page = box.page
        restored = normalized_to_canvas(
            box.x, box.y, box.w, box.h, page.image.width, page.image.height
        )

    for before, after in zip(original, restored, strict=True):
        assert after == pytest.approx(before, abs=1e-6)


def test_template_ids_are_preserved(legacy, monkeypatch):
    """The shipped iOS build refers to templates by number; renumbering breaks it."""
    db_path, uploads = legacy(
        [
            {"id": 3, "exam_name": "第三份", "pages": [{"image": "p", "annotations": []}]},
            {"id": 7, "exam_name": "第七份", "pages": [{"image": "p", "annotations": []}]},
        ]
    )
    run_import(monkeypatch, db_path, uploads)

    with SessionLocal() as db:
        assert sorted(t.id for t in db.query(ExamTemplate).all()) == [3, 7]
        assert db.get(ExamTemplate, 7).exam_name == "第七份"


def test_grade_and_subject_become_real_columns(legacy, monkeypatch):
    blank = [{"image": "p", "annotations": []}]
    db_path, uploads = legacy(
        [
            {"id": 1, "exam_name": "高一數學・段考一", "pages": blank},
            {"id": 2, "exam_name": "數甲 L1", "pages": blank},
        ]
    )
    run_import(monkeypatch, db_path, uploads)

    with SessionLocal() as db:
        classified = db.get(ExamTemplate, 1)
        assert (classified.grade, classified.subject) == ("高一", "數學")

        # The token scan cannot rescue a name that carries no token — the point
        # of a real column is that this one can now be fixed by hand once,
        # instead of being re-guessed wrongly by every client forever.
        unclassified = db.get(ExamTemplate, 2)
        assert unclassified.grade is None


def test_question_numbers_start_at_one_and_are_dense(legacy, monkeypatch):
    db_path, uploads = legacy(
        [
            {
                "id": 1,
                "exam_name": "六題選擇",
                "pages": [
                    {
                        "image": "p",
                        "annotations": [
                            {"class": "答案區", "bbox": [100, 50 * n, 60, 40], "answer": str(n)}
                            for n in range(1, 7)
                        ],
                    }
                ],
            }
        ]
    )
    run_import(monkeypatch, db_path, uploads)

    with SessionLocal() as db:
        boxes = db.query(AnswerBox).order_by(AnswerBox.question_no).all()
        assert [b.question_no for b in boxes] == [1, 2, 3, 4, 5, 6]
        assert [b.answer for b in boxes] == ["1", "2", "3", "4", "5", "6"]
        assert {b.answer_type for b in boxes} == {"digit"}


def test_rerunning_the_import_does_not_duplicate(legacy, monkeypatch):
    """Migrations get run twice. The second pass must be a no-op, not a mess."""
    db_path, uploads = legacy(
        [
            {
                "id": 1,
                "exam_name": "重跑測試",
                "pages": [
                    {"image": "p", "annotations": [
                        {"class": "答案區", "bbox": [100, 100, 60, 40], "answer": "5"}
                    ]}
                ],
            }
        ]
    )
    run_import(monkeypatch, db_path, uploads)
    run_import(monkeypatch, db_path, uploads)

    with SessionLocal() as db:
        assert db.query(ExamTemplate).count() == 1
        assert db.query(AnswerBox).count() == 1


def test_missing_image_file_is_skipped_not_fatal(legacy, monkeypatch, capsys):
    """A half-migrated database is worse than a reported gap."""
    db_path, uploads = legacy(
        [
            {"id": 1, "exam_name": "好的", "pages": [{"image": "p", "annotations": []}]},
            {"id": 2, "exam_name": "圖不見了", "pages": [{"image": "p", "annotations": []}]},
        ]
    )
    (uploads / "template_2.png").unlink()

    assert run_import(monkeypatch, db_path, uploads) == 0
    output = capsys.readouterr().out
    assert "匯入 1 份，略過 1 份" in output
    assert "找不到圖檔" in output

    with SessionLocal() as db:
        assert [t.id for t in db.query(ExamTemplate).all()] == [1]


def test_dry_run_writes_nothing(legacy, monkeypatch):
    db_path, uploads = legacy(
        [{"id": 1, "exam_name": "試跑", "pages": [{"image": "p", "annotations": []}]}]
    )
    assert run_import(monkeypatch, db_path, uploads, dry_run=True) == 0
    with SessionLocal() as db:
        assert db.query(ExamTemplate).count() == 0
