from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "FraudLens"
    environment: str = "development"
    # Mặc định dùng PostgreSQL của máy local (xem scripts/dev-db.ps1).
    # Đặt DATABASE_URL để trỏ sang Postgres khác / SQLite:
    #   postgresql+psycopg://user:pass@host:5432/fraudlens
    #   sqlite:///./data/fraudlens.db
    database_url: str = "postgresql+psycopg://postgres@127.0.0.1:5433/fraudlens"
    jwt_secret: str = "dev-only-change-me-in-production"
    access_token_minutes: int = 45
    refresh_token_days: int = 7
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    seed_on_start: bool = True
    demo_mode: bool = True
    cookie_secure: bool = False

    ai_enabled: bool = True
    ai_provider: str = "auto"  # auto | openai | openrouter | anthropic | offline
    ai_model: str = "gpt-4o-mini"
    # Để trống = dùng endpoint mặc định của provider. Ví dụ OpenRouter:
    #   AI_BASE_URL=https://openrouter.ai/api/v1
    ai_base_url: str = ""
    openai_api_key: str = ""
    openrouter_api_key: str = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-5-sonnet-latest"
    ai_timeout_seconds: float = 45.0
    # Danh sách model dự phòng (phẩy ngăn cách), thử lần lượt khi model chính lỗi.
    # Free tier của OpenRouter hay trả 429 nên nên khai báo 1-2 model free khác.
    ai_fallback_models: str = ""

    model_dir: Path = BASE_DIR / "app" / "ml" / "artifacts"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.environment.lower() in {"production", "prod"}


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
