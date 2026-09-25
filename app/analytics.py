"""Class statistics, as plain functions over plain data.

Kept free of the database so every number the reports and the AI quote can be
checked by a unit test. The routers gather rows; this decides what they mean.

Three rules run through all of it:

* The denominator is the paper, not the upload. A cell the camera never
  reached is missing from the upload, and dividing by what arrived would make
  a half-scanned paper look like a strong one. Scores are out of every choice
  and ○✕ question on the template.
* Only settled answers count. An answer is settled when `chosen` is set (the
  model committed, or a teacher read it); everything else is pending, and
  pending is reported, never folded into right or wrong.
* Small groups get counts, not rates. Below `SMALL_GROUP` papers, a
  percentage or a discrimination index says more than the data can.
"""

from __future__ import annotations

import math
import statistics
from collections import Counter
from dataclasses import dataclass, field

from .grading import BLANK, CIRCLE, CROSS, GRADED_TYPES, canonical

SMALL_GROUP = 10
GROUP_SHARE = 0.27          # Kelley's upper/lower 27%
SUSPECT_SHARE = 0.6         # one wrong option taken by this share of those answering
# Below this, a negative index is sampling noise in a class of thirty, not a
# question that rewards the weaker students.
NEGATIVE_D = -0.15


@dataclass(frozen=True)
class Item:
    question_no: int
    answer_type: str
    key: str


@dataclass
class Paper:
    session_id: int
    student_id: int | None
    # question_no → (chosen, verdict); questions never scanned are absent.
    answers: dict[int, tuple[str | None, str]] = field(default_factory=dict)


def graded_items(index: dict[int, tuple[str, str]]) -> list[Item]:
    return [Item(q, t, canonical(k)) for q, (t, k) in sorted(index.items()) if t in GRADED_TYPES]


def options_for(item: Item, option_count: int) -> list[str]:
    if item.answer_type == "mark":
        return [CIRCLE, CROSS]
    return [str(n) for n in range(1, option_count + 1)]


def paper_score(paper: Paper, items: list[Item]) -> dict:
    correct = pending = 0
    by_type = {t: [0, 0] for t in GRADED_TYPES}
    for item in items:
        chosen, verdict = paper.answers.get(item.question_no, (None, "unsure"))
        by_type[item.answer_type][1] += 1
        if chosen is None:
            pending += 1
        elif verdict == "correct":
            correct += 1
            by_type[item.answer_type][0] += 1
    return {"correct": correct, "total": len(items), "pending": pending,
            "choice": by_type["choice"], "mark": by_type["mark"]}


def _groups(papers: list[Paper], scores: dict[int, int]) -> tuple[list[Paper], list[Paper]]:
    """Upper and lower 27%, ties at the boundary included on both edges."""
    ranked = sorted(papers, key=lambda p: scores[p.session_id], reverse=True)
    cut = max(1, math.ceil(len(ranked) * GROUP_SHARE))
    high_floor = scores[ranked[cut - 1].session_id]
    low_ceiling = scores[ranked[-cut].session_id]
    high = [p for p in ranked if scores[p.session_id] >= high_floor]
    low = [p for p in ranked if scores[p.session_id] <= low_ceiling]
    return high, low


def _share(k: int, n: int) -> float | None:
    return round(k / n, 3) if n else None


def item_stats(item: Item, papers: list[Paper], option_count: int,
               groups: tuple[list[Paper], list[Paper]] | None) -> dict:
    options = options_for(item, option_count)
    counts: Counter[str] = Counter()
    correct = wrong = blank = pending = 0
    for paper in papers:
        chosen, verdict = paper.answers.get(item.question_no, (None, "unsure"))
        if chosen is None:
            pending += 1
        elif chosen == BLANK:
            blank += 1
        else:
            counts[chosen] += 1
            if verdict == "correct":
                correct += 1
            else:
                wrong += 1
    answered = correct + wrong + blank
    small = len(papers) < SMALL_GROUP

    wrong_options = [(o, c) for o, c in counts.most_common() if o != item.key]
    top_wrong = wrong_options[0] if wrong_options else None

    flags: list[str] = []
    # Everyone who answered took the same wrong option: in a class this is
    # rarely a coincidence, and the key is the first thing to check.
    if answered >= 2 and correct == 0 and top_wrong and top_wrong[1] == answered:
        flags.append("unanimous_wrong")
    if not small and top_wrong and answered and top_wrong[1] / answered >= SUSPECT_SHARE:
        flags.append("popular_distractor")
    if item.answer_type == "mark":
        flags.append("guessable")
        if not small and answered and correct / answered < 0.5:
            flags.append("below_chance")

    discrimination = None
    high_low = None
    if groups and not small:
        high, low = groups

        def rate(group: list[Paper]) -> float:
            right = sum(1 for p in group
                        if p.answers.get(item.question_no, (None, ""))[1] == "correct")
            return right / len(group)

        discrimination = round(rate(high) - rate(low), 3)
        if discrimination <= NEGATIVE_D:
            flags.append("negative_discrimination")

        def picks(group: list[Paper]) -> dict[str, int]:
            c = Counter(p.answers.get(item.question_no, (None, ""))[0] for p in group)
            return {o: c.get(o, 0) for o in options}

        high_low = {"high_n": len(high), "low_n": len(low),
                    "high": picks(high), "low": picks(low)}

    unchosen = [o for o in options if counts.get(o, 0) == 0 and o != item.key]
    return {
        "question_no": item.question_no,
        "answer_type": item.answer_type,
        "key": item.key,
        "papers": len(papers),
        "answered": answered,
        "correct": correct,
        "wrong": wrong,
        "blank": blank,
        "pending": pending,
        "correct_rate": None if small else _share(correct, answered),
        "options": {o: counts.get(o, 0) for o in options},
        "invalid": sum(c for o, c in counts.items() if o not in options),
        "top_wrong": {"option": top_wrong[0], "count": top_wrong[1]} if top_wrong else None,
        "unchosen": unchosen if not small else [],
        "discrimination": discrimination,
        "high_low": high_low,
        "flags": flags,
    }


def exam_report(items: list[Item], papers: list[Paper], option_count: int) -> dict:
    scores = {p.session_id: paper_score(p, items) for p in papers}
    correct_counts = [s["correct"] for s in scores.values()]
    small = len(papers) < SMALL_GROUP
    groups = (_groups(papers, {k: v["correct"] for k, v in scores.items()})
              if papers and not small else None)
    total = len(items)
    distribution = Counter(correct_counts)
    return {
        "papers": len(papers),
        "identified": sum(1 for p in papers if p.student_id is not None),
        "total": total,
        "small_group": small,
        "mean": round(statistics.fmean(correct_counts), 2) if correct_counts else None,
        "median": statistics.median(correct_counts) if correct_counts else None,
        "pending_cells": sum(s["pending"] for s in scores.values()),
        "distribution": [{"correct": k, "papers": distribution.get(k, 0)}
                         for k in range(total + 1)],
        "choice": _type_totals(scores, "choice"),
        "mark": _type_totals(scores, "mark"),
        "items": [item_stats(i, papers, option_count, groups) for i in items],
        "scores": {sid: s for sid, s in scores.items()},
    }


def _type_totals(scores: dict[int, dict], kind: str) -> dict:
    right = sum(s[kind][0] for s in scores.values())
    asked = sum(s[kind][1] for s in scores.values())
    return {"correct": right, "total": asked}
