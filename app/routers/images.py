from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import get_store
from ..models import Image, Teacher
from ..schemas import ImageOut
from ..security import current_teacher
from ..storage import BlobStore, UnsupportedImage

router = APIRouter(prefix="/api/v1/images", tags=["images"])


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
    _: Teacher = Depends(current_teacher),
) -> FileResponse:
    image = db.get(Image, image_id)
    if image is None:
        raise HTTPException(status_code=404, detail="找不到影像")
    path = store.path_for(image.sha256)
    if not path.is_file():
        raise HTTPException(status_code=410, detail="影像檔案已遺失")
    # Content-addressed, so the bytes behind this URL can never change: safe to
    # cache hard and forever.
    return FileResponse(
        path,
        media_type=image.mime,
        headers={"Cache-Control": "public, max-age=31536000, immutable", "ETag": image.sha256},
    )
