"""Who may touch which class, student and exam.

One place for these rules because every new endpoint needs them, and the AI
tools call the same functions: a question typed into a chat box must not be a
way to read another teacher's class.
"""

from __future__ import annotations

import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Enrollment, Exam, SchoolClass, Teacher


def owned_class(db: Session, teacher: Teacher, class_id: int) -> SchoolClass:
    school_class = db.get(SchoolClass, class_id)
    # 404 either way: another teacher's class is not something to confirm exists.
    if school_class is None or school_class.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="找不到班級")
    return school_class


def owned_exam(db: Session, teacher: Teacher, exam_uuid: uuid.UUID) -> Exam:
    exam = db.execute(select(Exam).where(Exam.client_uuid == exam_uuid)).scalar_one_or_none()
    if exam is None or exam.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="找不到這次考試")
    return exam


def teaches(db: Session, teacher: Teacher, student_id: int) -> bool:
    """Whether the student is on a roster this teacher owns."""
    return db.execute(
        select(Enrollment.id)
        .join(SchoolClass, SchoolClass.id == Enrollment.class_id)
        .where(Enrollment.student_id == student_id, SchoolClass.teacher_id == teacher.id)
        .limit(1)
    ).first() is not None
