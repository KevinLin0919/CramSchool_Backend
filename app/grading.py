"""What a student answered, in one spelling, and whether it was right.

The phone decides verdicts, but analysis cannot lean on them: a verdict is
fixed at upload against the key as it stood then, and the key can change. What
analysis needs is the answer itself — which option was chosen — in a form that
can be compared with any key, today's or next week's.

`canonical` is a port of `AnswerKind.canonical` in the iOS app
(AnswerRecognizer.swift). The two must agree, and `tests/test_grading.py`
pins the cases that matter.
"""

from __future__ import annotations

CIRCLE = "O"
CROSS = "X"

_CIRCLE_FORMS = {"O", "o", "○", "◯", "圈"}
# ✕ and ✖ are what the correction screen's buttons file; the app's own list
# was missing them, which marked a teacher's ✕ wrong against an X key.
_CROSS_FORMS = {"X", "x", "×", "✗", "✕", "✖", "叉"}
_CIRCLED_DIGITS = str.maketrans("⓪①②③④⑤⑥⑦⑧⑨", "0123456789")

# Dispositions the app stores in `teacher_value`. Not answers.
BLANK = "__blank__"
UNREADABLE = "__unreadable__"

GRADED_TYPES = ("choice", "mark")


def canonical(text: str | None) -> str:
    trimmed = (text or "").strip()
    if trimmed in _CIRCLE_FORMS:
        return CIRCLE
    if trimmed in _CROSS_FORMS:
        return CROSS
    return trimmed.translate(_CIRCLED_DIGITS)


def chosen(teacher_value: str | None, recognized: str | None, verdict: str,
           answer_type: str | None, option_count: int = 4) -> str | None:
    """The answer to count, or None when there is nothing trustworthy.

    A teacher's reading wins. Blank is an answer (the student left it empty);
    unreadable is not. Without a teacher's word, the model's reading counts
    only if it committed to a verdict — an unsure cell is exactly one it did
    not trust. A choice outside 1…option_count is a misread, not an option.
    """
    if teacher_value:
        if teacher_value == BLANK:
            return BLANK
        if teacher_value == UNREADABLE:
            return None
        value = canonical(teacher_value)
    elif verdict == "unsure" or not recognized:
        return None
    else:
        value = canonical(recognized)

    if answer_type == "choice":
        if not (value.isdigit() and 1 <= int(value) <= option_count):
            return None
    elif answer_type == "mark":
        if value not in (CIRCLE, CROSS):
            return None
    return value


def verdict_for(chosen_value: str | None, expected: str) -> str:
    """Right or wrong against a key, from the answer alone."""
    if chosen_value is None:
        return "unsure"
    if chosen_value == BLANK:
        return "wrong"
    return "correct" if chosen_value == canonical(expected) else "wrong"


def box_index(template) -> dict[int, tuple[str, str]]:
    """question_no → (answer_type, answer) for a template as it stands now.

    Question numbers run across the whole paper, so the first page holding a
    number wins; a duplicate on a later page would be a labelling error.
    """
    index: dict[int, tuple[str, str]] = {}
    for page in template.pages:
        for box in page.boxes:
            index.setdefault(box.question_no, (box.answer_type, box.answer))
    return index
