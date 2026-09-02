"""The migration's correctness rests entirely on this transform being exact.

If the round trip loses anything, every template imported from the old service
gets boxes that sit slightly off the answer cells — and the failure is silent,
because a box a few pixels adrift still looks like a box.
"""

import pytest

from app.coords import (
    CANVAS_HEIGHT,
    CANVAS_WIDTH,
    canvas_to_normalized,
    guess_answer_type,
    normalized_to_canvas,
)

# Portrait, landscape, square, and the exact 4:3 case where the letterbox
# vanishes — the boundary where an off-by-one in the padding would hide.
SHAPES = [(800, 1000), (1600, 1200), (1000, 1000), (2480, 3508), (640, 480)]


@pytest.mark.parametrize("width,height", SHAPES)
def test_canvas_round_trip_is_exact(width, height):
    original = [123.5, 88.25, 64.0, 40.5]
    x, y, w, h = canvas_to_normalized(original, width, height)
    restored = normalized_to_canvas(x, y, w, h, width, height)
    for before, after in zip(original, restored, strict=True):
        assert after == pytest.approx(before, abs=1e-9)


@pytest.mark.parametrize("width,height", SHAPES)
def test_normalized_round_trip_is_exact(width, height):
    original = (0.2, 0.35, 0.1, 0.05)
    canvas = normalized_to_canvas(*original, width, height)
    restored = canvas_to_normalized(canvas, width, height)
    for before, after in zip(original, restored, strict=True):
        assert after == pytest.approx(before, abs=1e-9)


def test_full_page_box_maps_to_the_drawn_area_not_the_whole_canvas():
    """A box covering the whole page must not claim the letterbox padding."""
    width, height = 800, 1000  # taller than 4:3, so padding is left/right
    canvas = normalized_to_canvas(0.0, 0.0, 1.0, 1.0, width, height)
    drawn_width = CANVAS_HEIGHT * width / height

    assert canvas[0] == pytest.approx((CANVAS_WIDTH - drawn_width) / 2)
    assert canvas[1] == pytest.approx(0.0)
    assert canvas[2] == pytest.approx(drawn_width)
    assert canvas[3] == pytest.approx(CANVAS_HEIGHT)


def test_square_canvas_case_has_no_vertical_padding():
    canvas = normalized_to_canvas(0.0, 0.0, 1.0, 1.0, 1000, 1000)
    assert canvas[3] == pytest.approx(CANVAS_HEIGHT)
    assert canvas[1] == pytest.approx(0.0)


def test_rejects_degenerate_image_dimensions():
    with pytest.raises(ValueError):
        canvas_to_normalized([0, 0, 10, 10], 0, 100)


@pytest.mark.parametrize(
    "answer,expected",
    [
        ("3", "digit"),
        ("144", "digit"),
        ("O", "mark"),
        ("✗", "mark"),
        ("怪", "chinese"),
        ("春眠不覺曉", "chinese"),
        ("", "text"),
        ("3a", "text"),
        ("A", "text"),
    ],
)
def test_answer_type_inference(answer, expected):
    assert guess_answer_type(answer) == expected


def test_inference_never_guesses_choice():
    """`choice` says the cell is a multiple-choice answer, which is a fact
    about the question, not about the answer written in it. A one-digit answer
    belongs equally to a fill-in blank, and marking that `choice` would throw
    away a second digit the student legitimately wrote — so this function,
    which exists to guess, is not allowed to guess it."""
    assert all(guess_answer_type(a) != "choice" for a in ["1", "4", "12", "0", ""])
