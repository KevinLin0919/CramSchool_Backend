"""Conversion between the legacy 800x600 canvas space and normalised 0..1.

Both existing clients place the master image into a fixed 800x600 canvas the
same way — scale to fit, then centre:

    scale   = min(800 / w, 600 / h)
    offsetX = (800 - w * scale) / 2
    offsetY = (600 - h * scale) / 2

(`CramSchoolWeb_Front_end/src/views/LabelView.vue:663` and
`AutoGradeScanner/NewTemplateView.swift:245` — independently written, same
convention.)

That makes the transform an affine map with no information loss, so migrating
old rows to fractions of the page is exact in both directions provided the
source image's pixel dimensions are known. They are: the image file is on disk
next to the row.

The letterbox is why the old space is worth leaving. A bbox in canvas space is
uninterpretable on its own — you need the image's aspect ratio to know how much
of it is padding — so every consumer had to re-derive the same offsets, and a
consumer that forgot produced boxes that looked plausible and sat slightly off
the answer cell.
"""

from __future__ import annotations

from dataclasses import dataclass

CANVAS_WIDTH = 800.0
CANVAS_HEIGHT = 600.0


@dataclass(frozen=True)
class Letterbox:
    scale: float
    offset_x: float
    offset_y: float
    drawn_width: float
    drawn_height: float

    @classmethod
    def for_image(cls, width: int, height: int) -> Letterbox:
        if width <= 0 or height <= 0:
            raise ValueError("image dimensions must be positive")
        scale = min(CANVAS_WIDTH / width, CANVAS_HEIGHT / height)
        drawn_w = width * scale
        drawn_h = height * scale
        return cls(
            scale=scale,
            offset_x=(CANVAS_WIDTH - drawn_w) / 2,
            offset_y=(CANVAS_HEIGHT - drawn_h) / 2,
            drawn_width=drawn_w,
            drawn_height=drawn_h,
        )


def canvas_to_normalized(
    bbox: list[float] | tuple[float, float, float, float],
    image_width: int,
    image_height: int,
) -> tuple[float, float, float, float]:
    """[x, y, w, h] in 800x600 canvas space -> fractions of the page image."""
    if len(bbox) < 4:
        raise ValueError("bbox must have four elements")
    x, y, w, h = (float(v) for v in bbox[:4])
    box = Letterbox.for_image(image_width, image_height)
    return (
        (x - box.offset_x) / box.drawn_width,
        (y - box.offset_y) / box.drawn_height,
        w / box.drawn_width,
        h / box.drawn_height,
    )


def normalized_to_canvas(
    x: float, y: float, w: float, h: float, image_width: int, image_height: int
) -> list[float]:
    """Fractions of the page image -> [x, y, w, h] in 800x600 canvas space."""
    box = Letterbox.for_image(image_width, image_height)
    return [
        x * box.drawn_width + box.offset_x,
        y * box.drawn_height + box.offset_y,
        w * box.drawn_width,
        h * box.drawn_height,
    ]


def guess_answer_type(answer: str) -> str:
    """Pick the recogniser an answer implies, for rows migrated without one.

    Deliberately conservative: anything that is not clearly a digit string or a
    circle/cross mark becomes 'text', because a wrong guess here silently routes
    a cell to a model that cannot read it.
    """
    value = (answer or "").strip()
    if not value:
        return "text"
    if value.isdigit():
        return "digit"
    if value in {"O", "o", "○", "◯", "圈", "X", "x", "✕", "✗", "×", "叉"}:
        return "mark"
    if all("一" <= ch <= "鿿" for ch in value):
        return "chinese"
    return "text"
