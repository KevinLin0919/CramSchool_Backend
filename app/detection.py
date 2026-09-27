"""QAT layout detection, bounded independently of the API's database work."""

import threading
from typing import Annotated

import httpx
from fastapi import HTTPException
from pydantic import BaseModel, Field, ValidationError, model_validator

from .config import Settings

MAX_BASE64_LENGTH = 20 * 1024 * 1024
_slots = threading.Semaphore(2)


class DetectionRequest(BaseModel):
    image_base64: str


Number = Annotated[float, Field(strict=True, allow_inf_nan=False)]


class Detection(BaseModel):
    bbox: tuple[Number, Number, Number, Number]
    confidence: Annotated[Number, Field(ge=0, le=1)]

    @model_validator(mode="after")
    def _ordered(self):
        x1, y1, x2, y2 = self.bbox
        if x2 <= x1 or y2 <= y1:
            raise ValueError("偵測框座標順序不正確")
        return self


class DetectionResponse(BaseModel):
    detections: list[Detection]


def detect_layout(
    payload: DetectionRequest,
    settings: Settings,
    *,
    transport: httpx.BaseTransport | None = None,
) -> DetectionResponse:
    if len(payload.image_base64) > MAX_BASE64_LENGTH:
        raise HTTPException(status_code=413, detail="影像編碼超過 20 MB 上限")
    if not settings.yolo_url:
        raise HTTPException(status_code=503, detail="此環境未啟用版面偵測")
    if not _slots.acquire(timeout=30):
        raise HTTPException(status_code=503, detail="偵測忙碌中，請稍後再試")
    try:
        with httpx.Client(timeout=90, transport=transport) as client:
            response = client.post(
                f"{settings.yolo_url.rstrip('/')}/predict",
                json={"image_base64": payload.image_base64},
            )
            response.raise_for_status()
            return DetectionResponse.model_validate(response.json())
    except (httpx.HTTPError, ValidationError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="版面偵測服務失敗，請稍後再試") from exc
    finally:
        _slots.release()
