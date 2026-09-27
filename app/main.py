from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .config import get_settings
from .limits import LimitBodySize
from .routers import ai, analytics, auth, classes, exams, images, sessions, students, templates

DESCRIPTION = """
補習班自動批改系統後端。

供 iOS App 使用。舊的 `/api/exam-templates` 介面已移除；
QAT 的模板編輯頁與班級報告共用登入。
舊格式的資料仍可用 `scripts/import_legacy.py` 一次性匯入。
"""


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings = get_settings()
    settings.blobs.mkdir(parents=True, exist_ok=True)
    settings.derivatives.mkdir(parents=True, exist_ok=True)
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    application = FastAPI(
        title="CramSchool Grading API",
        version="1.0.0",
        description=DESCRIPTION,
        lifespan=lifespan,
        docs_url="/docs" if settings.enable_docs else None,
        redoc_url="/redoc" if settings.enable_docs else None,
        openapi_url="/openapi.json" if settings.enable_docs else None,
    )

    # Outermost, deliberately. This has to see bytes before FastAPI reads the
    # body, which it does before any dependency — including the one that
    # checks who is asking.
    application.add_middleware(LimitBodySize, max_bytes=settings.max_request_bytes)

    if settings.cors_origins:
        application.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    application.include_router(auth.router)
    application.include_router(images.router)
    application.include_router(templates.router)
    application.include_router(sessions.router)
    application.include_router(students.router)
    application.include_router(classes.router)
    application.include_router(exams.router)
    application.include_router(analytics.router)
    application.include_router(ai.router)

    web_mounted = _mount_web(application, settings)
    label_mounted = _mount_label(application, settings)
    if web_mounted or label_mounted:
        _static_headers(application)

    @application.get("/health", tags=["ops"], summary="健康檢查")
    def health() -> dict:
        return {"status": "ok"}

    return application


def _mount_web(application: FastAPI, settings) -> bool:
    """The class report pages, same-origin with the API they read.

    Same origin is the point: the browser's bearer token is never offered to
    another host, and there is no CORS to get wrong. The headers are strict
    because this page holds a credential — no framing, no scripts from
    anywhere but here, and index.html never cached so a deploy is seen at once.
    """
    dist = Path(settings.web_dist)
    if not (dist / "index.html").is_file():
        return False

    application.mount("/web", StaticFiles(directory=dist, html=True), name="web")

    @application.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse("/web/")

    return True


def _mount_label(application: FastAPI, settings) -> bool:
    if not settings.label_dist:
        return False
    dist = Path(settings.label_dist)
    if not (dist / "index.html").is_file():
        return False
    application.mount("/label", StaticFiles(directory=dist, html=True), name="label")
    return True


def _static_headers(application: FastAPI) -> None:
    @application.middleware("http")
    async def static_headers(request: Request, call_next):
        response = await call_next(request)
        if any(request.url.path == prefix or request.url.path.startswith(prefix + "/")
               for prefix in ("/web", "/label")):
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
                "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'"
            )
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["Referrer-Policy"] = "no-referrer"
            response.headers["X-Content-Type-Options"] = "nosniff"
            if "/assets/" in request.url.path:
                response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            else:
                response.headers["Cache-Control"] = "no-cache"
        return response


app = create_app()
