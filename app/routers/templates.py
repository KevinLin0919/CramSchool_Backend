from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from ..config import Settings, get_settings
from ..db import get_db
from ..deps import get_store
from ..models import AnswerBox, ExamTemplate, Image, Teacher, TemplatePage
from ..schemas import (
    AnswerBoxOut,
    TemplateCreate,
    TemplateDetail,
    TemplateListResponse,
    TemplatePageIn,
    TemplatePageOut,
    TemplateSummary,
    TemplateUpdate,
)
from ..security import current_teacher
from ..storage import BlobStore

router = APIRouter(prefix="/api/v1/templates", tags=["templates"])


# ── serialisation ────────────────────────────────────────────────────────────


def _summary(template: ExamTemplate) -> TemplateSummary:
    return TemplateSummary(
        id=template.id,
        exam_name=template.exam_name,
        grade=template.grade,
        subject=template.subject,
        annotation_count=template.annotation_count,
        page_count=len(template.pages),
        revision=template.revision,
        created_at=template.created_at,
        updated_at=template.updated_at,
        deleted_at=template.deleted_at,
        master_url=f"/api/v1/templates/{template.id}/master" if template.pages else None,
    )


def detail(template: ExamTemplate) -> TemplateDetail:
    return TemplateDetail(
        **_summary(template).model_dump(),
        pages=[
            TemplatePageOut(
                page_index=page.page_index,
                image_id=page.image_id,
                image_width=page.image.width,
                image_height=page.image.height,
                boxes=[AnswerBoxOut.model_validate(b) for b in page.boxes],
            )
            for page in template.pages
        ],
    )


def _loaded(query):
    return query.options(
        selectinload(ExamTemplate.pages).selectinload(TemplatePage.boxes),
        selectinload(ExamTemplate.pages).selectinload(TemplatePage.image),
    )


def _get_or_404(db: Session, template_id: int, *, include_deleted: bool = False) -> ExamTemplate:
    template = db.execute(
        _loaded(select(ExamTemplate).where(ExamTemplate.id == template_id))
    ).scalar_one_or_none()
    if template is None or (template.deleted_at is not None and not include_deleted):
        raise HTTPException(status_code=404, detail="找不到考卷模板")
    return template


def _apply_pages(db: Session, template: ExamTemplate, pages: list[TemplatePageIn]) -> None:
    """Replace a template's pages wholesale.

    Rewriting rather than diffing is deliberate: the client always holds the
    complete intended state (it just came from the labeller), and a partial
    update protocol would need every box to carry a server-assigned id purely
    so the server could work out what the client already knows.
    """
    for image_id in {p.image_id for p in pages}:
        if db.get(Image, image_id) is None:
            raise HTTPException(status_code=400, detail=f"影像 {image_id} 不存在，請先上傳")

    template.pages.clear()
    db.flush()

    for page in sorted(pages, key=lambda p: p.page_index):
        row = TemplatePage(page_index=page.page_index, image_id=page.image_id)
        row.boxes = [
            AnswerBox(
                question_no=box.question_no,
                x=box.x,
                y=box.y,
                w=box.w,
                h=box.h,
                answer=box.answer,
                answer_type=box.answer_type,
                label=box.label,
            )
            for box in sorted(page.boxes, key=lambda b: b.question_no)
        ]
        template.pages.append(row)


# ── endpoints ────────────────────────────────────────────────────────────────


@router.get("", response_model=TemplateListResponse, summary="列出模板（支援增量同步）")
def list_templates(
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
    search: str | None = Query(default=None, description="關鍵字比對名稱"),
    grade: str | None = None,
    subject: str | None = None,
    updated_since: datetime | None = Query(
        default=None,
        description="只回傳這個時間之後變動的項目；刪除的會以 deleted_at 出現",
    ),
    limit: int = Query(default=500, ge=1, le=2000),
) -> TemplateListResponse:
    query = _loaded(select(ExamTemplate))

    if updated_since is not None:
        # Tombstones only make sense to a client that already has state, so a
        # cold start (no cursor) sees live templates only.
        query = query.where(ExamTemplate.updated_at > updated_since)
    else:
        query = query.where(ExamTemplate.deleted_at.is_(None))

    if search:
        like = f"%{search}%"
        query = query.where(or_(ExamTemplate.exam_name.ilike(like)))
    if grade:
        query = query.where(ExamTemplate.grade == grade)
    if subject:
        query = query.where(ExamTemplate.subject == subject)

    rows = db.execute(query.order_by(ExamTemplate.updated_at.desc()).limit(limit)).scalars().all()

    # The cursor is the newest row actually returned, not "now": if a write
    # lands between the query and the response, advancing to now would step
    # over it and the client would never see that change.
    cursor = max((r.updated_at for r in rows), default=None)
    return TemplateListResponse(templates=[_summary(r) for r in rows], sync_cursor=cursor)


@router.get("/{template_id}", response_model=TemplateDetail, summary="取得模板細節")
def get_template(
    template_id: int,
    response: Response,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> TemplateDetail:
    template = _get_or_404(db, template_id)
    response.headers["ETag"] = f'"{template.revision}"'
    return detail(template)


@router.post(
    "",
    response_model=TemplateDetail,
    status_code=status.HTTP_201_CREATED,
    summary="建立模板",
)
def create_template(
    payload: TemplateCreate,
    db: Session = Depends(get_db),
    teacher: Teacher = Depends(current_teacher),
) -> TemplateDetail:
    template = ExamTemplate(
        exam_name=payload.exam_name.strip(),
        grade=payload.grade,
        subject=payload.subject,
        created_by=teacher.id,
        revision=1,
    )
    db.add(template)
    db.flush()
    _apply_pages(db, template, payload.pages)
    db.commit()
    return detail(_get_or_404(db, template.id))


@router.patch("/{template_id}", response_model=TemplateDetail, summary="更新模板")
def update_template(
    template_id: int,
    payload: TemplateUpdate,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> TemplateDetail:
    """Optimistic locking via `If-Match: "<revision>"`.

    Two teachers can have the same template open. Without this the second save
    silently discards the first, and nobody finds out until a class is graded
    against boxes someone else deleted. Omitting the header is allowed for the
    single-editor case, so callers opt into the check.
    """
    template = _get_or_404(db, template_id)

    if if_match is not None:
        expected = if_match.strip().strip('"')
        if expected != str(template.revision):
            raise HTTPException(
                status_code=status.HTTP_412_PRECONDITION_FAILED,
                detail=f"模板已被其他人修改（伺服器版本 {template.revision}），請重新載入",
            )

    if payload.exam_name is not None:
        template.exam_name = payload.exam_name.strip()
    if payload.grade is not None:
        template.grade = payload.grade
    if payload.subject is not None:
        template.subject = payload.subject
    if payload.pages is not None:
        _apply_pages(db, template, payload.pages)

    template.revision += 1
    db.commit()
    return detail(_get_or_404(db, template_id))


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT, summary="刪除模板")
def delete_template(
    template_id: int,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Response:
    """Soft delete, so an offline phone can learn about it on next sync.

    The row is also kept because grading sessions reference it: hard-deleting a
    template would orphan every result ever graded against it.
    """
    template = _get_or_404(db, template_id)
    template.deleted_at = datetime.now(UTC)
    template.revision += 1
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{template_id}/master", summary="取得母卷影像（可指定寬度）")
def master_image(
    template_id: int,
    w: int | None = Query(default=None, description="縮放寬度；未指定則回原檔"),
    page: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    store: BlobStore = Depends(get_store),
    settings: Settings = Depends(get_settings),
    _: Teacher = Depends(current_teacher),
) -> FileResponse:
    """Server-side resizing.

    The device matcher runs at 832x608, so a 4000px original is bandwidth and
    battery spent on detail that is discarded on arrival. Widths are restricted
    to a fixed set — an open `?w=` lets anyone fill the disk with derivatives.
    """
    template = _get_or_404(db, template_id)
    target = next((p for p in template.pages if p.page_index == page), None)
    if target is None:
        raise HTTPException(status_code=404, detail="找不到該頁")

    if w is None:
        path = store.path_for(target.image.sha256)
        media_type = target.image.mime
        etag = target.image.sha256
    else:
        if w not in settings.allowed_master_widths:
            allowed = ", ".join(str(x) for x in settings.allowed_master_widths)
            raise HTTPException(status_code=400, detail=f"寬度僅支援：{allowed}")
        path = store.derivative(target.image.sha256, w)
        media_type = "image/jpeg"
        etag = f"{target.image.sha256}-{w}"

    if not path.is_file():
        raise HTTPException(status_code=410, detail="影像檔案已遺失")

    return FileResponse(
        path,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": etag},
    )
