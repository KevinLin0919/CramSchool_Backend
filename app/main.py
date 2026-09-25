from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .limits import LimitBodySize
from .routers import analytics, auth, classes, exams, images, sessions, students, templates

DESCRIPTION = """
補習班自動批改系統後端。

供 iOS App 使用。舊的 `/api/exam-templates` 介面已移除——網頁前端不再開發，
而舊格式的資料仍可用 `scripts/import_legacy.py` 一次性匯入。
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

    @application.get("/health", tags=["ops"], summary="健康檢查")
    def health() -> dict:
        return {"status": "ok"}

    return application


app = create_app()
