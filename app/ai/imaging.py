"""What of the master sheet the model is shown.

Not the whole page and a number: the printed numbering restarts each section
("一、是非題 1–15", "二、選擇題 1–10") while the app numbers questions straight
through, so "question 21" names a different printed question than the one the
model would find. Instead the strip around the question's own answer box is
cut out — the box's column, from just above it to the next box below — and a
small thumbnail of the page goes with it for context.
"""

from __future__ import annotations

import io

from PIL import Image as PILImage

from ..models import ExamTemplate


def _png(img: PILImage.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def question_strip(template: ExamTemplate, question_no: int, page_bytes: dict[int, bytes]
                   ) -> tuple[bytes, bytes] | None:
    for page in template.pages:
        box = next((b for b in page.boxes if b.question_no == question_no), None)
        if box is None:
            continue
        raw = page_bytes.get(page.image_id)
        if raw is None:
            return None
        img = PILImage.open(io.BytesIO(raw)).convert("RGB")
        width, height = img.size
        left_col = box.x + box.w / 2 < 0.5
        x0, x1 = (0.0, 0.52) if left_col else (0.48, 1.0)
        below = [b.y for b in page.boxes
                 if b.y > box.y + box.h * 0.5 and ((b.x + b.w / 2 < 0.5) == left_col)]
        y0 = max(0.0, box.y - box.h * 0.6)
        y1 = min(1.0, min(below) if below else box.y + 0.12)
        y1 = max(y1, box.y + box.h * 2)
        strip = img.crop((int(x0 * width), int(y0 * height), int(x1 * width), int(y1 * height)))
        if strip.width > 1400:
            strip = strip.resize((1400, int(strip.height * 1400 / strip.width)))
        thumb = img.copy()
        thumb.thumbnail((700, 700))
        return _png(strip), _png(thumb)
    return None
