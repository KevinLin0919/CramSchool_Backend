from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_store
from ..models import (
    ExamTemplate,
    GradedAnswer,
    GradingSession,
    Image,
    Teacher,
    TemplatePage,
)
from ..schemas import ImageOut
from ..security import current_teacher
from ..storage import BlobStore, UnsupportedImage

router = APIRouter(prefix="/api/v1/images", tags=["images"])


def _may_read(db: Session, image_id: int, teacher: Teacher) -> bool:
    """Whether this teacher has any business seeing these bytes.

    Holding a token used to be the whole test, and image ids are sequential,
    so anyone with a device could count from one and collect every scanned
    page, every cell crop of a child's handwriting, and every master sheet in
    the school. That made the per-teacher scoping on grading sessions
    cosmetic: the list refused to name the records, and the records' contents
    were one loop away.

    Two ways in, and nothing else:

    * a page of a template that still exists — answer keys are school-wide by
      design, every teacher grades against the same papers, and the master is
      the paper;
    * an image attached to a grading session this teacher owns: the page
      they photographed, its name field, or a crop of one cell of it.

    Deliberately not "any image referenced by any session": that is the hole,
    written as a rule.
    """
    is_template_page = db.execute(
        select(TemplatePage.id)
        .join(ExamTemplate, ExamTemplate.id == TemplatePage.template_id)
        .where(TemplatePage.image_id == image_id, ExamTemplate.deleted_at.is_(None))
        .limit(1)
    ).first()
    if is_template_page is not None:
        return True

    own_page = db.execute(
        select(GradingSession.id)
        .where(or_(GradingSession.image_id == image_id,
                   GradingSession.name_image_id == image_id),
               GradingSession.teacher_id == teacher.id)
        .limit(1)
    ).first()
    if own_page is not None:
        return True

    own_cell = db.execute(
        select(GradedAnswer.id)
        .join(GradingSession, GradingSession.id == GradedAnswer.session_id)
        .where(GradedAnswer.cell_image_id == image_id,
               GradingSession.teacher_id == teacher.id)
        .limit(1)
    ).first()
    return own_cell is not None


@router.head(
    "/sha256/{digest}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="問伺服器這張圖是否已存在",
)
def head_by_digest(
    digest: str,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Response:
    """Lets a client skip an upload it does not need to make.

    Hashing a few megabytes locally costs milliseconds; sending them over a
    cram school's uplink costs seconds. Every phone that syncs a template would
    otherwise re-upload the same master sheet.
    """
    image = db.execute(select(Image).where(Image.sha256 == digest.lower())).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="尚未上傳")
    return Response(status_code=status.HTTP_204_NO_CONTENT, headers={"X-Image-Id": str(image.id)})


@router.get("/sha256/{digest}", response_model=ImageOut, summary="以雜湊查詢影像")
def get_by_digest(
    digest: str,
    db: Session = Depends(get_db),
    _: Teacher = Depends(current_teacher),
) -> Image:
    image = db.execute(select(Image).where(Image.sha256 == digest.lower())).scalar_one_or_none()
    if image is None:
        raise HTTPException(status_code=404, detail="尚未上傳")
    return image


@router.post(
    "",
    response_model=ImageOut,
    status_code=status.HTTP_201_CREATED,
    summary="上傳影像（multipart）",
)
def upload_image(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    store: BlobStore = Depends(get_store),
    _: Teacher = Depends(current_teacher),
) -> Image:
    """multipart, not base64-in-JSON.

    The old endpoint took a data URL inside the request body, which inflates
    the payload by a third and forces the whole thing through the JSON parser
    as one string before anything can validate it.
    """
    data = file.file.read()
    try:
        blob = store.put(data)
    except UnsupportedImage as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    existing = db.execute(select(Image).where(Image.sha256 == blob.sha256)).scalar_one_or_none()
    if existing is not None:
        return existing

    image = Image(
        sha256=blob.sha256,
        mime=blob.mime,
        width=blob.width,
        height=blob.height,
        bytes=blob.bytes,
    )
    db.add(image)
    db.commit()
    db.refresh(image)
    return image


@router.get("/{image_id}/content", summary="下載影像原檔")
def image_content(
    image_id: int,
    db: Session = Depends(get_db),
    store: BlobStore = Depends(get_store),
    teacher: Teacher = Depends(current_teacher),
) -> FileResponse:
    image = db.get(Image, image_id)
    # 404 for "not yours" as well as "not there", deliberately. Ids are
    # sequential; a distinct 403 would turn this endpoint back into a way to
    # count how many papers the school has scanned.
    if image is None or not _may_read(db, image_id, teacher):
        raise HTTPException(status_code=404, detail="找不到影像")
    path = store.path_for(image.sha256)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="影像檔案已遺失")
    # Content-addressed, so the bytes behind this URL can never change: safe
    # to cache hard and forever. `private`, though, not `public` — the
    # response is the answer to an authenticated request, and `public` is the
    # exact opt-in that lets a shared cache keep it and hand it to the next
    # person who asks. It said `public` because the bytes are immutable,
    # which is true and is a different question.
    return FileResponse(
        path,
        media_type=image.mime,
        headers={
            "Cache-Control": "private, max-age=31536000, immutable",
            "Vary": "Authorization",
            "ETag": image.sha256,
        },
    )
