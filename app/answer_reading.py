"""Reading a master sheet's printed answers with Google Vision (QAT).

The same job the old OCR service's `/ocr_google` did for the web editor: crop
each answer cell from the master and ask Google Vision what is printed there,
so a teacher does not type the key by hand. Two differences from that service:
cells go to Google in batches rather than one request each, and no crop is
written to disk.

Off unless `GOOGLE_VISION_API_KEY` is set, like detection without `YOLO_URL`.
"""

import base64
import binascii
import io

import httpx
from fastapi import HTTPException
from PIL import Image as PILImage
from PIL import UnidentifiedImageError
from pydantic import BaseModel, Field

from .config import Settings
from .detection import MAX_BASE64_LENGTH

VISION_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"
# Google's per-request image limit for images:annotate.
BATCH = 16
MAX_CELLS = 200


class ReadAnswersRequest(BaseModel):
    image_base64: str
    # [x1, y1, x2, y2] in the image's pixels, as detection returns them.
    boxes: list[tuple[float, float, float, float]] = Field(max_length=MAX_CELLS)


class CellText(BaseModel):
    text: str


class ReadAnswersResponse(BaseModel):
    results: list[CellText]


def _crops(image: PILImage.Image, boxes) -> list[str | None]:
    """PNG base64 of each cell, or None where the box has no area on the page."""
    width, height = image.size
    out: list[str | None] = []
    for x1, y1, x2, y2 in boxes:
        left, top = max(0, int(x1)), max(0, int(y1))
        right, bottom = min(width, int(x2)), min(height, int(y2))
        if right <= left or bottom <= top:
            out.append(None)
            continue
        buffer = io.BytesIO()
        image.crop((left, top, right, bottom)).save(buffer, format="PNG")
        out.append(base64.b64encode(buffer.getvalue()).decode())
    return out


def read_answers(
    payload: ReadAnswersRequest,
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> ReadAnswersResponse:
    if len(payload.image_base64) > MAX_BASE64_LENGTH:
        raise HTTPException(status_code=413, detail="影像編碼超過 20 MB 上限")
    if not settings.google_vision_api_key:
        raise HTTPException(status_code=503, detail="正解辨識尚未啟用")
    try:
        image = PILImage.open(io.BytesIO(base64.b64decode(payload.image_base64, validate=True)))
        image = image.convert("RGB")
    except (binascii.Error, ValueError, UnidentifiedImageError, OSError) as exc:
        raise HTTPException(status_code=400, detail="無法讀取影像") from exc

    crops = _crops(image, payload.boxes)
    texts = [""] * len(crops)
    wanted = [i for i, c in enumerate(crops) if c is not None]
    try:
        with httpx.Client(timeout=30, transport=transport) as client:
            for start in range(0, len(wanted), BATCH):
                chunk = wanted[start:start + BATCH]
                response = client.post(
                    VISION_ENDPOINT,
                    params={"key": settings.google_vision_api_key},
                    json={"requests": [
                        {"image": {"content": crops[i]},
                         "features": [{"type": "DOCUMENT_TEXT_DETECTION"}]}
                        for i in chunk
                    ]},
                )
                response.raise_for_status()
                answers = response.json().get("responses", [])
                for i, answer in zip(chunk, answers, strict=False):
                    # A cell Google could not read stays blank for the teacher
                    # to fill; its error message is not theirs to act on.
                    if isinstance(answer, dict) and "error" not in answer:
                        texts[i] = str(answer.get("fullTextAnnotation", {}).get("text", "")).strip()
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="正解辨識服務失敗，請稍後再試") from exc
    return ReadAnswersResponse(results=[CellText(text=t) for t in texts])
