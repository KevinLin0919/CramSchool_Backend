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

    # ── Microsoft Entra sign-in ─────────────────────────────────────────
    # Both come from the school's app registration. Empty means the endpoint
    # reports itself unconfigured rather than half-working.
    microsoft_tenant_id: str = ""
    microsoft_client_id: str = ""

    # Whether anyone in the tenant may sign in, or only accounts already
    # present as teachers.
    #
    # Defaults to False on purpose. A directory holds more than teachers —
    # reception, admin accounts, the owner's personal login — and this
    # service stores every answer key in the school. Being in the address
    # book is not a reason to be handed those. Turning it on is a decision
    # someone should make deliberately, so it is a setting rather than the
    # default.
    microsoft_auto_provision: bool = False

    # How long a device token issued through Microsoft lasts.
    #
    # Without an expiry, disabling someone's Microsoft account does not
    # revoke the token already on their iPad — the whole central-offboarding
    # argument for using Entra at all would be false. Thirty days bounds how
    # long a departed account keeps working while leaving daily use offline.
    microsoft_token_days: int = 30

    # Signing keys are cached; Microsoft rotates them, so the cache has to
    # expire and has to tolerate a key it has never seen.
    jwks_cache_seconds: int = 12 * 60 * 60

    cors_origins: tuple[str, ...] = ()

    @property
    def microsoft_configured(self) -> bool:
        return bool(self.microsoft_tenant_id and self.microsoft_client_id)

    @property
    def microsoft_issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self.microsoft_tenant_id}/v2.0"

    @property
    def microsoft_jwks_url(self) -> str:
        return (f"https://login.microsoftonline.com/{self.microsoft_tenant_id}"
                "/discovery/v2.0/keys")

    @property
    def derivatives(self) -> Path:
        return self.derivative_cache_dir or (self.data_dir / "derivatives")

    @property
    def blobs(self) -> Path:
        return self.data_dir / "blobs"


@lru_cache
def get_settings() -> Settings:
    return Settings()
