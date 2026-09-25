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

    # The hard ceiling on a request body, applied before anything reads it.
    # Above `max_upload_bytes` on purpose: the image endpoint's own limit is
    # about what is a sensible scan, this is about what this process will
    # tolerate at all, and a multipart envelope is slightly larger than the
    # file inside it.
    max_request_bytes: int = 30 * 1024 * 1024

    # Whether to serve the interactive API docs.
    #
    # Off by default, which is the right way round once this is reachable
    # from outside: nothing behind /docs is secret — the shipped app binary
    # contains every path — but publishing the map costs nothing to withhold.
    enable_docs: bool = False

    # The built web report (web/dist), served under /web when present. The
    # image puts it here; a bare checkout has none, and the API runs without.
    web_dist: str = "/srv/web_dist"

    # AI, through OpenCode Zen. Empty key means the AI endpoints answer 503
    # "not configured" and everything else works as before.
    opencode_api_key: str = ""
    opencode_base_url: str = "https://opencode.ai/zen/v1"
    # `anthropic` for Claude (/messages), `openai` for GPT (/responses).
    ai_model: str = "claude-sonnet-5"
    ai_api_style: str = "anthropic"
    # USD per million tokens, for the budget and the log. Upper bounds.
    ai_price_in: float = 4.0
    ai_price_out: float = 15.0
    ai_daily_budget_usd: float = 3.0
    ai_max_concurrent: int = 2
    ai_timeout_seconds: float = 60.0
    # Off by default: it sends a child's handwritten name to a third party.
    # QAT turns it on for role-played students.
    ai_name_suggestions: bool = False

    # ── 對外開放端點的速率限制 ──────────────────────────────────────────
    # Only two endpoints accept a request without a token, and both of them do
    # real work per call. These numbers are generous by design: redeeming an
    # invite code happens once in a device's life, and signing in happens once
    # a month. A teacher will never come near them.
    auth_rate_limit_per_ip: int = 10
    auth_rate_limit_overall: int = 60
    auth_rate_limit_window_seconds: int = 60

    # Whose `X-Forwarded-For` to believe. Empty means nobody's — the peer
    # address is then the only thing counted, which is correct when this
    # process is reached directly.
    #
    # Behind Tailscale Funnel this must be the compose bridge GATEWAY,
    # 172.31.240.1 — measured, not 127.0.0.1 as this comment used to say.
    # Funnel connects to the loopback-published port, and Docker hands a
    # loopback connection to the container through its userland proxy, which
    # re-originates it from the bridge. So every caller on the internet
    # arrives as 172.31.240.1, and without this the per-caller limit is one
    # bucket shared by the whole internet.
    #
    # Trusting it is safe because nothing else can arrive from there: LAN and
    # tailnet clients reach the container through iptables DNAT with their
    # own addresses intact. Funnel appends the real caller to the header, and
    # `ratelimit.client_key` takes the rightmost entry — the one Funnel wrote
    # — so a caller who sends their own `X-Forwarded-For` changes nothing.
    # Both halves were checked end to end through the public relay.
    trusted_proxies: tuple[str, ...] = ()

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
