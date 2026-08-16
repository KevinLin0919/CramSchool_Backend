"""One-shot import from the Flask/SQLite template service.

Reads the old `templates.db` plus its `uploads/templates/` directory and writes
the same content into the new schema. Safe to re-run: templates are matched on
their original id, so a second pass updates rather than duplicates.

Two things are recovered rather than copied:

* **Coordinates.** The old rows are in 800x600 canvas space with letterbox
  padding baked in. Undoing that needs the source image's pixel dimensions,
  which is why the image file is opened rather than trusted — and it is exact,
  so nothing is approximated here (`app/coords.py`).
* **Grade and subject.** These never existed as columns; the iOS client
  recovered them by scanning the exam name for known tokens. The same scan runs
  once here so the values become real data instead of being re-derived on every
  client, forever.

Usage:
    python -m scripts.import_legacy --legacy-db /data/templates.db \\
                                    --legacy-uploads /data/uploads/templates
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import select

# Same token lists as AutoGradeScanner/Models.swift, applied once at import
# time rather than on every client on every launch.
GRADE_TOKENS = ["國一", "國二", "國三", "高一", "高二", "高三",
                "小一", "小二", "小三", "小四", "小五", "小六"]
SUBJECT_TOKENS = ["數學", "英文", "英語", "國文", "理化", "物理", "化學",
                  "歷史", "地理", "生物", "自然", "社會", "公民"]


def classify(exam_name: str) -> tuple[str | None, str | None]:
    grade = next((t for t in GRADE_TOKENS if t in exam_name), None)
    subject = next((t for t in SUBJECT_TOKENS if t in exam_name), None)
    return grade, subject


def parse_timestamp(raw: str) -> datetime:
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return datetime.now()


def main() -> int:
    parser = argparse.ArgumentParser(description="從舊的模板服務匯入資料")
    parser.add_argument("--legacy-db", required=True, type=Path)
    parser.add_argument("--legacy-uploads", required=True, type=Path)
    parser.add_argument(
        "--dry-run", action="store_true", help="只檢查與回報，不寫入"
    )
    args = parser.parse_args()

    if not args.legacy_db.is_file():
        print(f"找不到舊資料庫：{args.legacy_db}", file=sys.stderr)
        return 1

    from app.coords import canvas_to_normalized, guess_answer_type
    from app.db import SessionLocal
    from app.deps import get_store
    from app.models import AnswerBox, ExamTemplate, Image, TemplatePage

    store = get_store()
    legacy = sqlite3.connect(str(args.legacy_db))
    legacy.row_factory = sqlite3.Row
    rows = legacy.execute(
        "SELECT id, exam_name, image_path, pages, created_at FROM exam_templates ORDER BY id"
    ).fetchall()

    imported = skipped = 0
    problems: list[str] = []

    with SessionLocal() as db:
        for row in rows:
            image_file = args.legacy_uploads / Path(row["image_path"]).name
            if not image_file.is_file():
                problems.append(f"#{row['id']} {row['exam_name']}：找不到圖檔 {image_file.name}")
                skipped += 1
                continue

            try:
                pages_payload = json.loads(row["pages"])
            except json.JSONDecodeError as exc:
                problems.append(f"#{row['id']} {row['exam_name']}：pages 不是合法 JSON（{exc}）")
                skipped += 1
                continue

            if args.dry_run:
                boxes = sum(len(p.get("annotations", [])) for p in pages_payload)
                print(f"  #{row['id']:<4} {row['exam_name']:<28} {boxes} 格")
                imported += 1
                continue

            blob = store.put(image_file.read_bytes())
            image = db.execute(
                select(Image).where(Image.sha256 == blob.sha256)
            ).scalar_one_or_none()
            if image is None:
                image = Image(
                    sha256=blob.sha256,
                    mime=blob.mime,
                    width=blob.width,
                    height=blob.height,
                    bytes=blob.bytes,
                )
                db.add(image)
                db.flush()

            # Preserve the original id: the shipped iOS build and anything the
            # web app bookmarked refer to templates by number.
            template = db.get(ExamTemplate, row["id"])
            if template is None:
                grade, subject = classify(row["exam_name"])
                template = ExamTemplate(
                    id=row["id"],
                    exam_name=row["exam_name"],
                    grade=grade,
                    subject=subject,
                    created_at=parse_timestamp(row["created_at"]),
                    revision=1,
                )
                db.add(template)
                db.flush()
            else:
                template.pages.clear()
                db.flush()

            for page_index, page in enumerate(pages_payload):
                page_row = TemplatePage(page_index=page_index, image_id=image.id)
                boxes = []
                for question_no, annotation in enumerate(page.get("annotations", []), start=1):
                    bbox = annotation.get("bbox") or []
                    if len(bbox) < 4:
                        problems.append(
                            f"#{row['id']} 第 {question_no} 格 bbox 不完整，已略過"
                        )
                        continue
                    x, y, w, h = canvas_to_normalized(bbox, blob.width, blob.height)
                    answer = (annotation.get("answer") or "").strip()
                    boxes.append(
                        AnswerBox(
                            question_no=question_no,
                            x=x, y=y, w=w, h=h,
                            answer=answer,
                            answer_type=guess_answer_type(answer),
                            label=annotation.get("class") or "答案區",
                        )
                    )
                page_row.boxes = boxes
                template.pages.append(page_row)

            imported += 1

        if not args.dry_run:
            db.commit()

            # SQLite AUTOINCREMENT and Postgres sequences both need nudging
            # past explicitly-inserted ids, or the next create collides.
            if db.bind.dialect.name == "postgresql" and rows:
                from sqlalchemy import text
                db.execute(
                    text(
                        "SELECT setval(pg_get_serial_sequence('exam_templates','id'), "
                        "(SELECT COALESCE(MAX(id),1) FROM exam_templates))"
                    )
                )
                db.commit()

    legacy.close()

    print(f"\n{'（試跑）' if args.dry_run else ''}匯入 {imported} 份，略過 {skipped} 份")
    if problems:
        print(f"\n需要注意的 {len(problems)} 項：")
        for note in problems:
            print(f"  - {note}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
