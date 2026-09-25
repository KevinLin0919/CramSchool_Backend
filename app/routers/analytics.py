"""Reports over a teacher's own classes.

Everything here is read-only and scoped through `app.scope`, and the numbers
come from `app.analytics`. The AI tools call these same loaders, so a report
on screen and an answer in the chat panel cannot disagree.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..analytics import Paper, exam_report, graded_items, options_for, paper_score
from ..db import get_db
from ..grading import BLANK, box_index
from ..models import Exam, ExamTemplate, GradingSession, Student, Teacher, TemplatePage
from ..scope import owned_class, owned_exam, teaches
from ..security import current_teacher

router = APIRouter(prefix="/api/v1", tags=["analytics"])


def load_exam(db: Session, exam: Exam):
    template = db.execute(
        select(ExamTemplate)
        .options(selectinload(ExamTemplate.pages).selectinload(TemplatePage.boxes))
        .where(ExamTemplate.id == exam.template_id)
    ).scalar_one()
    items = graded_items(box_index(template))
    sessions = db.execute(
        select(GradingSession).options(selectinload(GradingSession.answers))
        .where(GradingSession.exam_id == exam.id)
        .order_by(GradingSession.scanned_at)
    ).scalars().all()
    papers = [
        Paper(session_id=s.id, student_id=s.student_id,
              answers={a.question_no: (a.chosen, a.verdict) for a in s.answers})
        for s in sessions
    ]
    return template, items, sessions, papers


def _names(db: Session, ids) -> dict[int, str]:
    ids = [i for i in ids if i is not None]
    if not ids:
        return {}
    return dict(db.execute(select(Student.id, Student.name).where(Student.id.in_(ids))).all())


def build_report(db: Session, exam: Exam) -> dict:
    template, items, sessions, papers = load_exam(db, exam)
    report = exam_report(items, papers, template.option_count)
    names = _names(db, [s.student_id for s in sessions])
    scores = report.pop("scores")
    report["exam"] = {
        "uuid": str(exam.client_uuid), "class_id": exam.class_id,
        "class_name": exam.school_class.name, "is_simulated": exam.school_class.is_simulated,
        "template_id": template.id, "template_name": template.exam_name,
        "unit": template.unit, "exam_date": exam.exam_date.isoformat(), "sitting": exam.sitting,
    }
    report["paper_list"] = [
        {"session_uuid": str(s.client_uuid), "student_id": s.student_id,
         "student_name": names.get(s.student_id), "correct": scores[s.id]["correct"],
         "pending": scores[s.id]["pending"]}
        for s in sessions
    ]
    return report


@router.get("/exams/{client_uuid}/report", summary="考試報告")
def exam_report_endpoint(client_uuid: uuid.UUID, db: Session = Depends(get_db),
                         teacher: Teacher = Depends(current_teacher)) -> dict:
    return build_report(db, owned_exam(db, teacher, client_uuid))


@router.get("/exams/{client_uuid}/items/{question_no}/students",
            summary="每個選項是哪些學生選的")
def item_students(client_uuid: uuid.UUID, question_no: int, db: Session = Depends(get_db),
                  teacher: Teacher = Depends(current_teacher)) -> dict:
    exam = owned_exam(db, teacher, client_uuid)
    template, items, sessions, _ = load_exam(db, exam)
    item = next((i for i in items if i.question_no == question_no), None)
    if item is None:
        raise HTTPException(status_code=404, detail="這份考卷沒有這一題（或不是選擇、是非題）")
    names = _names(db, [s.student_id for s in sessions])
    groups: dict[str, list[dict]] = {o: [] for o in options_for(item, template.option_count)}
    groups.update({BLANK: [], "pending": []})
    for s in sessions:
        answer = next((a for a in s.answers if a.question_no == question_no), None)
        key = answer.chosen if answer and answer.chosen is not None else "pending"
        groups.setdefault(key, []).append(
            {"session_uuid": str(s.client_uuid), "student_name": names.get(s.student_id)})
    return {"question_no": question_no, "key": item.key, "groups": groups}


def class_trend(db: Session, class_id: int) -> dict:
    exams = db.execute(
        select(Exam).where(Exam.class_id == class_id)
    ).scalars().all()
    rows = []
    per_student: dict[int, list[dict]] = {}
    for exam in exams:
        template, items, sessions, papers = load_exam(db, exam)
        if not papers:
            continue
        scored = [paper_score(p, items) for p in papers]
        total = len(items) or 1
        entry = {
            "exam_uuid": str(exam.client_uuid), "unit": template.unit,
            "template_name": template.exam_name, "exam_date": exam.exam_date.isoformat(),
            "papers": len(papers),
            "mean_rate": round(sum(s["correct"] for s in scored) / (total * len(scored)), 3),
            "choice_rate": _rate(scored, "choice"), "mark_rate": _rate(scored, "mark"),
        }
        rows.append(entry)
        for paper, score in zip(papers, scored, strict=True):
            if paper.student_id is not None:
                per_student.setdefault(paper.student_id, []).append({
                    "exam_uuid": entry["exam_uuid"], "unit": template.unit,
                    "rate": round(score["correct"] / total, 3),
                    "choice": score["choice"], "mark": score["mark"],
                })
    rows.sort(key=lambda r: (r["unit"] or "", r["exam_date"]))
    names = _names(db, per_student)
    return {"exams": rows, "students": [
        {"student_id": sid, "student_name": names.get(sid), "results": res}
        for sid, res in sorted(per_student.items())
    ]}


def _rate(scored: list[dict], kind: str) -> float | None:
    right = sum(s[kind][0] for s in scored)
    asked = sum(s[kind][1] for s in scored)
    return round(right / asked, 3) if asked else None


@router.get("/classes/{class_id}/trend", summary="班級各單元趨勢")
def class_trend_endpoint(class_id: int, db: Session = Depends(get_db),
                         teacher: Teacher = Depends(current_teacher)) -> dict:
    owned_class(db, teacher, class_id)
    return class_trend(db, class_id)


def student_profile(db: Session, teacher: Teacher, student_id: int) -> dict:
    if not teaches(db, teacher, student_id):
        raise HTTPException(status_code=404, detail="找不到學生")
    student = db.get(Student, student_id)
    sessions = db.execute(
        select(GradingSession).options(selectinload(GradingSession.answers))
        .where(GradingSession.student_id == student_id,
               GradingSession.teacher_id == teacher.id,
               GradingSession.exam_id.is_not(None))
        .order_by(GradingSession.scanned_at)
    ).scalars().all()
    results = []
    for s in sessions:
        exam = db.get(Exam, s.exam_id)
        template, items, _, _ = load_exam(db, exam)
        paper = Paper(s.id, s.student_id, {a.question_no: (a.chosen, a.verdict) for a in s.answers})
        score = paper_score(paper, items)
        keys = {i.question_no: i.key for i in items}
        wrong = [{"question_no": a.question_no, "chosen": a.chosen, "key": keys[a.question_no]}
                 for a in s.answers
                 if a.question_no in keys and a.chosen is not None and a.verdict == "wrong"]
        results.append({"exam_uuid": str(exam.client_uuid), "unit": template.unit,
                        "template_name": template.exam_name,
                        "exam_date": exam.exam_date.isoformat(), **score, "wrong": wrong})
    return {"student_id": student_id, "student_name": student.name if student else None,
            "results": results}


@router.get("/students/{student_id}/profile", summary="學生歷次表現")
def student_profile_endpoint(student_id: int, db: Session = Depends(get_db),
                             teacher: Teacher = Depends(current_teacher)) -> dict:
    return student_profile(db, teacher, student_id)
