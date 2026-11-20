"""Application configuration loaded from environment variables (never hard-coded secrets)."""
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(PROJECT_ROOT / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    app_name: str = "MediCore AI"
    api_prefix: str = "/api"

    jwt_secret_key: str = Field(default="change-me", min_length=8)
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    database_url: str = f"sqlite:///{(BACKEND_DIR / 'medicore.db').as_posix()}"

    cors_origins: str = "http://localhost:5173"

    models_dir: Path = PROJECT_ROOT / "models"
    data_dir: Path = PROJECT_ROOT / "data"

    max_upload_mb: int = 10

    gemini_api_key: str | None = None
    gemini_model: str = "gemini-2.5-flash"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"

    nominatim_url: str = "https://nominatim.openstreetmap.org"
    # comma-separated; tried in order
    overpass_url: str = ("https://overpass-api.de/api/interpreter,"
                         "https://overpass.private.coffee/api/interpreter")
    osm_user_agent: str = "MediCoreAI/0.1 (educational project)"

    rate_limit_enabled: bool = True
    # Shared rate-limit storage for multiple workers/instances (e.g. redis://redis:6379/0). In-memory if unset.
    redis_url: str | None = None

    log_level: str = "INFO"
    log_format: str = "text"            # "json" in production for log aggregation
    # Interactive API docs (/api/docs). Defaults to off in production unless explicitly enabled.
    enable_docs: bool | None = None
    # Comma-separated Host header allow-list (production); "*" disables the check.
    allowed_hosts: str = "*"
    web_concurrency: int = 2

    frontend_url: str = "http://localhost:5173"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None

    @field_validator("models_dir", "data_dir", mode="after")
    @classmethod
    def _resolve(cls, v: Path) -> Path:
        return v if v.is_absolute() else (BACKEND_DIR / v).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def docs_enabled(self) -> bool:
        return (not self.is_production) if self.enable_docs is None else self.enable_docs

    @property
    def allowed_host_list(self) -> list[str]:
        return [h.strip() for h in self.allowed_hosts.split(",") if h.strip()]


class ConfigError(RuntimeError):
    pass


def validate_production(s: Settings) -> list[str]:
    """Refuse to start in production with unsafe settings."""
    problems = []
    if s.jwt_secret_key in ("change-me", "") or len(s.jwt_secret_key) < 32:
        problems.append("JWT_SECRET_KEY must be a random value of at least 32 characters")
    if s.database_url.startswith("sqlite"):
        problems.append("DATABASE_URL must point to PostgreSQL in production (SQLite is for development only)")
    if any(o == "*" for o in s.cors_origin_list):
        problems.append("CORS_ORIGINS must list explicit origins, not '*'")
    if "example.com" in s.osm_user_agent.lower():
        problems.append("OSM_USER_AGENT must identify your deployment (OpenStreetMap rejects example.com contacts)")
    if s.web_concurrency > 1 and not s.redis_url and s.rate_limit_enabled:
        problems.append("REDIS_URL is required for consistent rate limiting with more than one worker")
    return problems


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.is_production and (problems := validate_production(s)):
        raise ConfigError("Unsafe production configuration: " + "; ".join(problems))
    return s
