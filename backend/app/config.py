"""Application settings, loaded from environment variables only."""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "sqlite:///./billwise.db"

    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_timeout_seconds: float = 30.0
    # Leave blank for auto: OpenRouter when the key starts with sk-or-, else OpenAI.
    openai_base_url: str = ""

    agent_max_tool_iterations: int = 4
    agent_max_tool_calls: int = 8
    ai_rate_limit_requests: int = 15
    ai_rate_limit_window_seconds: int = 60

    app_env: str = "development"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    demo_user_email: str = "amina@demo.billwise.ai"
    seed_on_startup: bool = True

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def llm_enabled(self) -> bool:
        """True when a real API key is configured on the backend."""
        return bool(self.openai_api_key.strip())

    @property
    def is_openrouter(self) -> bool:
        key = self.openai_api_key.strip()
        if self.openai_base_url.strip():
            return "openrouter.ai" in self.openai_base_url.lower()
        return key.startswith("sk-or-")

    @property
    def resolved_openai_base_url(self) -> str | None:
        explicit = self.openai_base_url.strip()
        if explicit:
            return explicit
        if self.is_openrouter:
            return "https://openrouter.ai/api/v1"
        return None


@lru_cache
def get_settings() -> Settings:
    return Settings()
