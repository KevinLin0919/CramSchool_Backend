"""The server's reading of an answer must match the app's."""

import pytest

from app.grading import BLANK, UNREADABLE, canonical, chosen, verdict_for


@pytest.mark.parametrize("raw,expected", [
    ("O", "O"), ("o", "O"), ("○", "O"), ("◯", "O"), ("圈", "O"),
    ("X", "X"), ("x", "X"), ("×", "X"), ("✗", "X"), ("叉", "X"),
    # What the correction screen files. The app's list lacked these.
    ("✕", "X"), ("✖", "X"),
    ("①", "1"), ("④", "4"), (" 3 ", "3"), ("", ""),
])
def test_canonical_matches_the_app(raw, expected):
    assert canonical(raw) == expected


def test_a_teacher_reading_wins_over_the_model():
    assert chosen("2", "3", "wrong", "choice") == "2"


def test_an_unsure_reading_is_not_an_answer():
    assert chosen(None, "3", "unsure", "choice") is None


def test_blank_is_an_answer_and_unreadable_is_not():
    assert chosen(BLANK, "3", "unsure", "choice") == BLANK
    assert chosen(UNREADABLE, "3", "wrong", "choice") is None
    assert verdict_for(BLANK, "2") == "wrong"
    assert verdict_for(None, "2") == "unsure"


def test_a_choice_outside_the_options_is_a_misread():
    assert chosen(None, "7", "wrong", "choice", option_count=4) is None
    assert chosen(None, "0", "wrong", "choice") is None


def test_a_cross_filed_by_the_correction_screen_is_right_against_an_x_key():
    picked = chosen("✕", None, "unsure", "mark")
    assert verdict_for(picked, "X") == "correct"
