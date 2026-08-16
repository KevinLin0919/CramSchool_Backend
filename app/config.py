from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Postgres in production; SQLite keeps `pytest` and a bare `uvicorn` run
    # working with no services attached. Every query goes through SQLAlchemy
    # precisely so this stays a one-line decision.
    database_url: str = "sqlite:///./dev.db"

    # Content-addressed image store. One directory, sharded two levels deep by
    # the digest so no single directory holds a hundred thousand entries.
    data_dir: Path = Path("./data")

    # Derived sizes (the ?w= query on master images) are a cache, not data:
    # deleting this directory must only cost CPU, never content.
    derivative_cache_dir: Path | None = None

    # Uploads larger than this are rejected before being read into memory.
    max_upload_bytes: int = 25 * 1024 * 1024

    # The widths the master-image endpoint will render. An open-ended ?w=
    # lets anyone fill the disk with derivatives.
    allowed_master_widths: tuple[int, ...] = (640, 1024, 1600, 2048)

    # Bootstrap: creates an admin + prints a token on first startup when the
    # teachers table is empty. Leave unset in production and use `cramctl`.
    bootstrap_admin_email: str | None = None

    cors_origins: tuple[str, ...] = ()

    @property
    def derivatives(self) -> Path:
        return self.derivative_cache_dir or (self.data_dir / "derivatives")

    @property
    def blobs(self) -> Path:
        return self.data_dir / "blobs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
