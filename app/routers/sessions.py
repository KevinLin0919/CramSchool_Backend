import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..db import get_db
from ..models import ExamTemplate, GradedAnswer, GradingSession, Image, Student, Teacher
from ..schemas import (
    GradedAnswerOut,
    GradingSessionIn,
    GradingSessionOut,
    GradingSessionSummary,
)
from ..security import current_teacher

router = APIRouter(prefix="/api/v1/grading-sessions", tags=["grading"])


def _out(session: GradingSession, template_name: str | None) -> GradingSessionOut:
    return GradingSessionOut(
        id=session.id,
        client_uuid=session.client_uuid,
        template_id=session.template_id,
        template_name=template_name,
        student_id=session.student_id,
        teacher_id=session.teacher_id,
        image_id=session.image_id,
        scanned_at=session.scanned_at,
        uploaded_at=session.uploaded_at,
        correct_count=session.correct_count,
        total_count=session.total_count,
        app_version=session.app_version,
        answers=[GradedAnswerOut.model_validate(a) for a in session.answers],
    )


@router.put(
    "/{client_uuid}",
    response_model=GradingSessionOut,
    summary="上傳批改結果（冪等）",
)
def upsert_session(
    client_uuid: uuid.UUID,
    payload: GradingSessionIn,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(current_teacher),
) -> GradingSessionOut:
    """PUT on a client-minted UUID, so retrying is always safe.

    A phone on cram-school Wi-Fi will lose a response it already succeeded in
    sending. With POST the retry creates a second copy of the same graded
    paper and the class register quietly gains a duplicate; with PUT the retry
    lands on the row the first attempt created.

    That also makes this the natural endpoint for a teacher's later
    corrections: re-uploading the same session with `teacher_value` filled in
    updates it in place.
    """
    template = db.get(ExamTemplate, payload.template_id)
    if template is None or template.deleted_at is not None:
        raise HTTPException(status_code=400, detail="考卷模板不存在")
    if payload.student_id is not None and db.get(Student, payload.student_id) is None:
        raise HTTPException(status_code=400, detail="學生不存在")
    for image_id in filter(None, [payload.image_id, *(a.cell_image_id for a in payload.answers)]):
        if db.get(Image, image_id) is None:
            raise HTTPException(status_code=400, detail=f"影像 {image_id} 不存在，請先上傳")

    session = db.execute(
        select(GradingSession)
        .options(selectinload(GradingSession.answers))
        .where(GradingSession.client_uuid == client_uuid)
    ).scalar_one_or_none()

    created = session is None
    if session is None:
        session = GradingSession(client_uuid=client_uuid)
        db.add(session)

    session.template_id = payload.template_id
    session.student_id = payload.student_id
    session.teacher_id = teacher.id
    session.image_id = payload.image_id
    session.scanned_at = payload.scanned_at
    session.uploaded_at = datetime.now(UTC)
    session.app_version = payload.app_version

    # Counts are derived, never trusted from the client: a phone that crashed
    # mid-session could otherwise report a score its own answers contradict.
    session.correct_count = sum(1 for a in payload.answers if a.verdict == "correct")
    session.total_count = len(payload.answers)

    previous = {a.question_no: a for a in session.answers}
    session.answers.clear()
    db.flush()

    for answer in sorted(payload.answers, key=lambda a: a.question_no):
        prior = previous.get(answer.question_no)
        # Keep the first correction's timestamp: it records when a human
        # actually looked at the cell, which is what makes the row usable as
        # training data later.
        corrected_at = None
        if answer.teacher_value:
            corrected_at = (
                prior.corrected_at
                if prior is not None and prior.teacher_value == answer.teacher_value
                else datetime.now(UTC)
            )
        session.answers.append(
            GradedAnswer(
                question_no=answer.question_no,
                expected=answer.expected,
                recognized=answer.recognized,
                verdict=answer.verdict,
                confidence=answer.confidence,
                margin=answer.margin,
                teacher_value=answer.teacher_value,
                corrected_at=corrected_at,
                cell_image_id=answer.cell_image_id,
            )
        )

    db.commit()
    db.refresh(session)
    response = _out(session, template.exam_name)
    if created:
        return response
    return response


@router.get("", response_model=list[GradingSessionSummary], summary="查詢批改紀錄")
def list_sessions(
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
    student_id: int | None = None,
    template_id: int | None = None,
    since: datetime | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> list[GradingSessionSummary]:
    query = select(GradingSession, ExamTemplate.exam_name).join(
        ExamTemplate, ExamTemplate.id == GradingSession.template_id
    )
    if student_id is not None:
        query = query.where(GradingSession.student_id == student_id)
    if template_id is not None:
        query = query.where(GradingSession.template_id == template_id)
    if since is not None:
        query = query.where(GradingSession.scanned_at >= since)

    rows = db.execute(query.order_by(GradingSession.scanned_at.desc()).limit(limit)).all()
    return [
        GradingSessionSummary(
            id=s.id,
            client_uuid=s.client_uuid,
            template_id=s.template_id,
            template_name=name,
            student_id=s.student_id,
            scanned_at=s.scanned_at,
            correct_count=s.correct_count,
            total_count=s.total_count,
        )
        for s, name in rows
    ]


@router.get("/{client_uuid}", response_model=GradingSessionOut, summary="取得單筆批改紀錄")
def get_session(
    client_uuid: uuid.UUID,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> GradingSessionOut:
    session = db.execute(
        select(GradingSession)
        .options(selectinload(GradingSession.answers))
        .where(GradingSession.client_uuid == client_uuid)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="找不到批改紀錄")
    template = db.get(ExamTemplate, session.template_id)
    return _out(session, template.exam_name if template else None)


@router.delete("/{client_uuid}", status_code=status.HTTP_204_NO_CONTENT, summary="刪除批改紀錄")
def delete_session(
    client_uuid: uuid.UUID,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Response:
    session = db.execute(
        select(GradingSession).where(GradingSession.client_uuid == client_uuid)
    ).scalar_one_or_none()
    if session is None:
        raise HTTPException(status_code=404, detail="找不到批改紀錄")
    db.delete(session)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── 訓練資料匯出 ─────────────────────────────────────────────────────────────


@router.get("/exports/corrections", summary="匯出老師修正過的格子（訓練資料）")
def export_corrections(
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
    since: datetime | None = None,
    limit: int = Query(default=5000, ge=1, le=50000),
) -> list[dict]:
    """Every cell a teacher overrode, with its crop — a labelled dataset.

    This is the point of storing `teacher_value` alongside `cell_image_id`.
    The recogniser was tuned against six hand-labelled cells; ordinary use for
    a term produces thousands, gathered as a by-product of grading rather than
    as a separate annotation effort.
    """
    query = (
        select(GradedAnswer, GradingSession.scanned_at)
        .join(GradingSession, GradingSession.id == GradedAnswer.session_id)
        .where(GradedAnswer.teacher_value.isnot(None))
        .where(GradedAnswer.cell_image_id.isnot(None))
    )
    if since is not None:
        query = query.where(GradedAnswer.corrected_at >= since)

    rows = db.execute(query.order_by(GradedAnswer.corrected_at.desc()).limit(limit)).all()
    return [
        {
            "cell_image_id": answer.cell_image_id,
            "cell_image_url": f"/api/v1/images/{answer.cell_image_id}/content",
            "label": answer.teacher_value,
            "model_read": answer.recognized,
            "expected": answer.expected,
            "confidence": answer.confidence,
            "margin": answer.margin,
            "scanned_at": scanned_at.isoformat(),
        }
        for answer, scanned_at in rows
    ]
