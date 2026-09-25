"""AI endpoints. Each returns a run at once; the page polls it."""

import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..ai import service
from ..ai.provider import AIError, AINotConfigured, Provider
from ..ai.provider import Image as AIImage
from ..config import Settings, get_settings
from ..db import get_db
from ..models import InsightRun, Teacher
from ..scope import owned_class, owned_exam
from ..security import current_teacher

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class AskIn(BaseModel):
    question: str = Field(min_length=2, max_length=300)


@router.get("/status", summary="AI 是否可用")
def ai_status(_: Teacher = Depends(current_teacher),
              settings: Settings = Depends(get_settings)) -> dict:
    return service.status(settings)


@router.post("/exams/{exam_uuid}/items/{question_no}/explain", summary="解釋這一題")
def explain(exam_uuid: uuid.UUID, question_no: int, background: BackgroundTasks,
            db: Session = Depends(get_db), teacher: Teacher = Depends(current_teacher)) -> dict:
    exam = owned_exam(db, teacher, exam_uuid)
    run = service.start(db, teacher.id, exam, "explain", str(question_no),
                        service.explain_item(exam.id, question_no), background.add_task)
    return service.run_out(run)


@router.post("/exams/{exam_uuid}/summary", summary="考試摘要")
def summary(exam_uuid: uuid.UUID, background: BackgroundTasks,
            db: Session = Depends(get_db), teacher: Teacher = Depends(current_teacher)) -> dict:
    exam = owned_exam(db, teacher, exam_uuid)
    run = service.start(db, teacher.id, exam, "summary", None,
                        service.summarize_exam(exam.id), background.add_task)
    return service.run_out(run)


@router.post("/exams/{exam_uuid}/ask", summary="問這次考試")
def ask(exam_uuid: uuid.UUID, payload: AskIn, background: BackgroundTasks,
        db: Session = Depends(get_db), teacher: Teacher = Depends(current_teacher)) -> dict:
    exam = owned_exam(db, teacher, exam_uuid)
    question = payload.question.strip()
    run = service.start(db, teacher.id, exam, "ask", question,
                        service.ask(exam.id, teacher.id, question), background.add_task)
    return service.run_out(run)


@router.get("/runs/{run_id}", summary="取得 AI 結果")
def get_run(run_id: int, db: Session = Depends(get_db),
            teacher: Teacher = Depends(current_teacher)) -> dict:
    run = db.get(InsightRun, run_id)
    if run is None or run.teacher_id != teacher.id:
        raise HTTPException(status_code=404, detail="找不到")
    return service.run_out(run)


@router.post("/name-suggestion", summary="姓名欄 → 名冊中最像的學生")
def name_suggestion(
    class_id: int = Form(...),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(current_teacher),
    settings: Settings = Depends(get_settings),
) -> dict:
    """A suggestion only; the teacher confirms every match on the phone.

    Off unless AI_NAME_SUGGESTIONS is on, because it sends a child's
    handwriting to a third party. Synchronous: one short call, answered while
    the matching screen is open.
    """
    if not settings.ai_name_suggestions:
        raise HTTPException(status_code=403, detail="姓名建議未開啟")
    cls = owned_class(db, teacher, class_id)
    roster = sorted((e.student for e in cls.enrollments), key=lambda s: s.id)
    if not roster:
        return {"suggestions": []}
    png = image.file.read(2_000_000)
    listing = "\n".join(f"{i + 1}. {s.name}" for i, s in enumerate(roster))
    prompt = ("圖片是考卷上的姓名欄，學生手寫。下面是這個班的名冊，請判斷最可能是誰。"
              "字可能很潦草，只從名冊中選。\n" + listing +
              "\n回答 JSON：{\"ranking\": [{\"n\": 名冊編號, \"score\": 0 到 1 的可能性}]}，"
              "最多三個，看不出來就回空陣列。")
    try:
        reply = Provider(settings).complete(service.SYSTEM_BASE, [
            {"role": "user", "text": prompt, "images": [AIImage(png)]}], max_tokens=200)
        data = service._parse_json(reply.text)
    except AINotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except AIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    out = []
    for entry in data.get("ranking", [])[:3]:
        n = int(entry.get("n", 0))
        if 1 <= n <= len(roster):
            out.append({"student_id": roster[n - 1].id, "name": roster[n - 1].name,
                        "score": round(float(entry.get("score", 0)), 2)})
    return {"suggestions": out}
