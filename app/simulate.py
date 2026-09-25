"""A simulated class, for showing what the reports look like with a full room.

Three real students cannot fill a distribution chart, and a demo that passes
invented numbers off as real ones is worse than no demo. So this builds a
clearly flagged class (`is_simulated`) under the demo teacher, and one command
removes it again.

The answers are not uniform noise, which a judge spots at a glance. Each
student has an ability that grows a little from unit to unit; each question has
a difficulty and a discrimination (a two-parameter logistic model, with a
guessing floor for ○✕ questions); a student who misses a choice question is
drawn to one tempting wrong option more than the others. Two questions are
planted for the demo script: one where most of the class takes the same wrong
option, and one ○✕ question close to a coin toss.
"""

from __future__ import annotations

import math
import random
import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from .grading import BLANK, CIRCLE, CROSS, box_index, canonical, verdict_for
from .models import (
    Enrollment,
    Exam,
    ExamTemplate,
    GradedAnswer,
    GradingSession,
    SchoolClass,
    Student,
    TemplatePage,
)

NAMES = [
    "王柏睿", "李品妍", "張宸瑋", "劉芷晴", "陳冠宇", "楊語彤", "黃承恩", "趙子晴", "吳宥辰",
    "周亭妤", "徐靖翔", "孫以晴", "馬浩宇", "朱芸熙", "胡家豪", "郭沛瑜", "何宇翔", "高詠晴",
    "林睿哲", "羅苡安", "鄭博文", "梁宜蓁", "謝昀澔", "宋思妤", "唐宥翔", "許心妍", "韓鈞皓",
    "馮雨桐",
]

BLANK_RATE = 0.02
PENDING_RATE = 0.03


def _p_correct(theta: float, a: float, b: float, floor: float) -> float:
    return floor + (1 - floor) / (1 + math.exp(-1.7 * a * (theta - b)))


def seed(db: Session, teacher_id: int, templates: list[ExamTemplate], *,
         class_name: str = "四年乙班（模擬）", size: int = 28, rng_seed: int = 20261005,
         last_date: date | None = None) -> SchoolClass:
    rng = random.Random(rng_seed)
    school_class = SchoolClass(teacher_id=teacher_id, name=class_name, is_simulated=True)
    db.add(school_class)
    db.flush()
    students = []
    for name in NAMES[:size]:
        student = Student(name=name)
        db.add(student)
        db.flush()
        db.add(Enrollment(class_id=school_class.id, student_id=student.id))
        students.append((student, rng.gauss(0, 1)))

    last_date = last_date or date.today()
    for unit_index, template in enumerate(templates):
        template = db.execute(
            select(ExamTemplate)
            .options(selectinload(ExamTemplate.pages).selectinload(TemplatePage.boxes))
            .where(ExamTemplate.id == template.id)
        ).scalar_one()
        exam_day = last_date - timedelta(days=7 * (len(templates) - 1 - unit_index))
        exam = Exam(client_uuid=uuid.uuid4(), teacher_id=teacher_id, class_id=school_class.id,
                    template_id=template.id, exam_date=exam_day)
        db.add(exam)
        db.flush()

        index = box_index(template)
        graded = [(q, t, canonical(k)) for q, (t, k) in sorted(index.items())
                  if t in ("choice", "mark")]
        params = {}
        choice_qs = [q for q, t, _ in graded if t == "choice"]
        mark_qs = [q for q, t, _ in graded if t == "mark"]
        for q, t, key in graded:
            if t == "choice":
                options = [str(n) for n in range(1, template.option_count + 1)]
                distractors = [o for o in options if o != key]
                lure = rng.choice(distractors)
                weights = [3.0 if d == lure else 1.0 for d in distractors]
                params[q] = (rng.uniform(0.8, 1.8), rng.gauss(0, 0.8), 0.0, distractors, weights)
            else:
                params[q] = (rng.uniform(0.6, 1.4), rng.gauss(-0.4, 0.7), 0.5, None, None)

        # The demo's two stories, placed in the middle unit.
        planted_lure = planted_coin = None
        if unit_index == len(templates) // 2:
            if choice_qs:
                planted_lure = choice_qs[len(choice_qs) // 2]
            if mark_qs:
                planted_coin = mark_qs[len(mark_qs) // 2]

        for student, ability in students:
            theta = ability + 0.4 * unit_index
            minute = rng.randint(0, 90)
            session = GradingSession(
                client_uuid=uuid.uuid4(), template_id=template.id, teacher_id=teacher_id,
                student_id=student.id, exam_id=exam.id, identity_source="teacher",
                identified_at=datetime.now(UTC), app_version="simulated",
                scanned_at=datetime.combine(exam_day, time(8, 0), tzinfo=UTC)
                + timedelta(minutes=minute),
            )
            db.add(session)
            db.flush()
            correct = 0
            for q, t, key in graded:
                a, b, floor, distractors, weights = params[q]
                roll = rng.random()
                if roll < PENDING_RATE:
                    chosen, verdict = None, "unsure"
                elif roll < PENDING_RATE + BLANK_RATE:
                    chosen, verdict = BLANK, "wrong"
                else:
                    if q == planted_lure:
                        right = rng.random() < 0.12
                        wrong_pick = distractors[weights.index(max(weights))]
                        chosen = key if right else (wrong_pick if rng.random() < 0.85
                                                    else rng.choice(distractors))
                    elif q == planted_coin:
                        flipped = CROSS if key == CIRCLE else CIRCLE
                        chosen = key if rng.random() < 0.48 else flipped
                    elif rng.random() < _p_correct(theta, a, b, floor):
                        chosen = key
                    elif t == "choice":
                        chosen = rng.choices(distractors, weights=weights)[0]
                    else:
                        chosen = CROSS if key == CIRCLE else CIRCLE
                    verdict = verdict_for(chosen, key)
                correct += verdict == "correct"
                db.add(GradedAnswer(
                    session_id=session.id, question_no=q, expected=key,
                    recognized=None if chosen in (None, BLANK) else chosen,
                    teacher_value=BLANK if chosen == BLANK else None,
                    verdict=verdict, answer_type=t, chosen=chosen,
                ))
            session.correct_count = correct
            session.total_count = len(graded)
    db.commit()
    return school_class


def purge(db: Session, teacher_id: int | None = None) -> int:
    """Remove every simulated class and everything hanging off it."""
    query = select(SchoolClass).where(SchoolClass.is_simulated.is_(True))
    if teacher_id is not None:
        query = query.where(SchoolClass.teacher_id == teacher_id)
    classes = db.execute(query).scalars().all()
    for school_class in classes:
        exam_ids = [e for (e,) in db.execute(
            select(Exam.id).where(Exam.class_id == school_class.id))]
        if exam_ids:
            for session in db.execute(
                select(GradingSession).where(GradingSession.exam_id.in_(exam_ids))
            ).scalars():
                db.delete(session)
            db.execute(delete(Exam).where(Exam.id.in_(exam_ids)))
        student_ids = [s for (s,) in db.execute(
            select(Enrollment.student_id).where(Enrollment.class_id == school_class.id))]
        db.delete(school_class)
        db.flush()
        for sid in student_ids:
            still_enrolled = db.execute(
                select(Enrollment.id).where(Enrollment.student_id == sid).limit(1)).first()
            if still_enrolled is None:
                db.execute(delete(Student).where(Student.id == sid))
    db.commit()
    return len(classes)
