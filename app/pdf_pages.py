"""A PDF answer key, as the page images the template editor already works on.

Scanned answer keys arrive as PDFs more often than as photos: the school's
copier writes one, and publishers ship their 教用 keys as one. The editor only
knows images, so each page is rendered here to the same JPEG it would have
made from a photo, and the teacher picks which pages make up the paper.

Rendered on the server rather than in the browser. pdfium is Chrome's own
engine: a key typeset in a CJK font needs CMaps, a copier scan is often JBIG2
or JPX, and doing either in the page means shipping fonts, a worker and a CSP
exception for WebAssembly. Here it is one library call.

Bounded because a PDF is a program of sorts: one render at a time, a cap on
the file, the page count and the pixels per page.
"""

from __future__ import annotations

import base64
import io
import threading

import pypdfium2 as pdfium
from fastapi import HTTPException, status
from pydantic import BaseModel

MAX_PDF_BYTES = 30 * 1024 * 1024
MAX_PAGES = 20
# The same long side the editor scales a photo to, so a page from a PDF and
# a page from the camera roll are indistinguishable downstream.
LONG_SIDE = 2400
_slots = threading.Semaphore(1)


class PdfPage(BaseModel):
    page_no: int  # 1-based, as a PDF viewer numbers it
    width: int
    height: int
    image_base64: str  # JPEG


class PdfPagesResponse(BaseModel):
    page_count: int
    pages: list[PdfPage]


def render_pdf(data: bytes) -> PdfPagesResponse:
    if len(data) > MAX_PDF_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="PDF 超過 30 MB 上限")
    if b"%PDF" not in data[:1024]:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="這不是 PDF 檔案")
    if not _slots.acquire(timeout=30):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="正在處理另一份 PDF，請稍後再試")
    try:
        try:
            document = pdfium.PdfDocument(data)
        except pdfium.PdfiumError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="無法讀取這份 PDF（可能有密碼或檔案損毀）") from exc
        try:
            count = len(document)
            if count == 0:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                    detail="這份 PDF 沒有頁面")
            if count > MAX_PAGES:
                raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                    detail=f"PDF 超過 {MAX_PAGES} 頁，請先拆出這份考卷的頁面")
            return PdfPagesResponse(page_count=count,
                                    pages=[_render(document, i) for i in range(count)])
        finally:
            document.close()
    finally:
        _slots.release()


def _render(document: pdfium.PdfDocument, index: int) -> PdfPage:
    page = document[index]
    try:
        width, height = page.get_size()  # points, with the page's own rotation applied
        if min(width, height) <= 0 or max(width, height) / min(width, height) > 20:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"第 {index + 1} 頁的尺寸異常，無法轉成圖片")
        image = page.render(scale=LONG_SIDE / max(width, height)).to_pil().convert("RGB")
        out = io.BytesIO()
        image.save(out, "JPEG", quality=90)
        return PdfPage(page_no=index + 1, width=image.width, height=image.height,
                       image_base64=base64.b64encode(out.getvalue()).decode())
    finally:
        page.close()
