"""Sittings: one class taking one paper on one day.

The phone mints the UUID so a stack can be started with no network. Two phones
starting the same sitting offline will mint two UUIDs; the second one to reach
the server is told about the first, and files its papers there instead.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..grading import GRADED_TYPES, box_index, chosen, verdict_for
from ..models import Exam, ExamTemplate, GradingSession, SchoolClass, Teacher, TemplatePage
from ..schemas import ExamIn, ExamOut
from ..scope import owned_class, owned_exam
from ..security import current_teacher

router = APIRouter(prefix="/api/v1/exams", tags=["exams"])


def exam_out(db: Session, exam: Exam) -> ExamOut:
    papers, identified = db.execute(
        select(func.count(GradingSession.id), func.count(GradingSession.student_id))
        .where(GradingSession.exam_id == exam.id)
    ).one()
    return ExamOut(
        client_uuid=exam.client_uuid,
        class_id=exam.class_id,
        class_name=exam.school_class.name,
        template_id=exam.template_id,
        template_name=exam.template.exam_name,
        unit=exam.template.unit,
        exam_date=exam.exam_date,
        sitting=exam.sitting,
        is_simulated=exam.school_class.is_simulated,
        paper_count=papers,
        identified_count=identified,
    )


@router.put("/{client_uuid}", response_model=ExamOut, summary="開始或取得一次考試（冪等）")
def upsert_exam(client_uuid: uuid.UUID, payload: ExamIn, db: Session = Depends(get_db),
                teacher: Teacher = Depends(current_teacher)) -> ExamOut:
    existing = db.execute(select(Exam).where(Exam.client_uuid == client_uuid)).scalar_one_or_none()
    if existing is not None:
        if existing.teacher_id != teacher.id:
            raise HTTPException(status_code=404, detail="找不到這次考試")
        return exam_out(db, existing)

    owned_class(db, teacher, payload.class_id)
    template = db.get(ExamTemplate, payload.template_id)
    if template is None or template.deleted_at is not None:
        raise HTTPException(status_code=400, detail="考卷模板不存在")

    # Same sitting started elsewhere first. The response carries that one's
    # UUID, and a client that sees a different UUID come back files there.
    same = db.execute(select(Exam).where(
        Exam.teacher_id == teacher.id, Exam.class_id == payload.class_id,
        Exam.template_id == payload.template_id, Exam.exam_date == payload.exam_date,
        Exam.sitting == payload.sitting,
    )).scalar_one_or_none()
    if same is not None:
        return exam_out(db, same)

    exam = Exam(client_uuid=client_uuid, teacher_id=teacher.id, class_id=payload.class_id,
                template_id=payload.template_id, exam_date=payload.exam_date,
                sitting=payload.sitting)
    db.add(exam)
    db.commit()
    db.refresh(exam)
    return exam_out(db, exam)


@router.get("", response_model=list[ExamOut], summary="我的考試")
def list_exams(db: Session = Depends(get_db),
               teacher: Teacher = Depends(current_teacher)) -> list[ExamOut]:
    rows = db.execute(
        select(Exam).join(SchoolClass, SchoolClass.id == Exam.class_id)
        .where(Exam.teacher_id == teacher.id)
        .order_by(Exam.exam_date.desc(), Exam.id.desc())
    ).scalars().all()
    return [exam_out(db, e) for e in rows]


@router.get("/{client_uuid}", response_model=ExamOut)
def get_exam(client_uuid: uuid.UUID, db: Session = Depends(get_db),
             teacher: Teacher = Depends(current_teacher)) -> ExamOut:
    return exam_out(db, owned_exam(db, teacher, client_uuid))


@router.post("/{client_uuid}/regrade", response_model=ExamOut,
             summary="依目前的標準答案重新計分")
def regrade(client_uuid: uuid.UUID, db: Session = Depends(get_db),
            teacher: Teacher = Depends(current_teacher)) -> ExamOut:
    """After an answer key is fixed, bring this sitting's results in line.

    Verdicts were fixed at upload against the key as it was. Re-deciding them
    from `chosen` — what the student actually answered — needs nothing from
    the phone. Cells nobody could read stay undecided.
    """
    exam = owned_exam(db, teacher, client_uuid)
    template = db.execute(
        select(ExamTemplate)
        .options(selectinload(ExamTemplate.pages).selectinload(TemplatePage.boxes))
        .where(ExamTemplate.id == exam.template_id)
    ).scalar_one()
    index = box_index(template)
    sessions = db.execute(
        select(GradingSession).options(selectinload(GradingSession.answers))
        .where(GradingSession.exam_id == exam.id)
    ).scalars().all()
    for session in sessions:
        for answer in session.answers:
            answer_type, key = index.get(answer.question_no, (answer.answer_type, answer.expected))
            answer.answer_type = answer_type
            answer.expected = key
            if answer_type in GRADED_TYPES:
                answer.chosen = chosen(answer.teacher_value, answer.recognized, answer.verdict,
                                       answer_type, template.option_count)
                if answer.chosen is not None:
                    answer.verdict = verdict_for(answer.chosen, key)
        session.correct_count = sum(1 for a in session.answers if a.verdict == "correct")
        session.uploaded_at = datetime.now(UTC)
    db.commit()
    return exam_out(db, exam)
