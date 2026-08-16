from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .routers import auth, images, sessions, students, templates

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
    )

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

    @application.get("/health", tags=["ops"], summary="健康檢查")
    def health() -> dict:
        return {"status": "ok"}

    return application


app = create_app()
