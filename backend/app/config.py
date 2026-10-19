"""Runtime settings, read from environment variables or the repo-root .env file."""

import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///./sme_finance.db"

    # LLM. Default: Z.ai GLM free tier through its OpenAI-compatible API.
    llm_base_url: str = "https://api.z.ai/api/paas/v4"
    llm_api_key: str = ""
    llm_model: str = "glm-4.5-flash"
    llm_fallback_models: str = "glm-4.7-flash"  # comma-separated, tried in order
    llm_extra_body: str = '{"thinking": {"type": "disabled"}}'  # provider-specific JSON
    llm_max_retries: int = 2  # per model, on 429 / 5xx / timeout
    llm_timeout_seconds: float = 30
    agent_max_steps: int = 8

    # Security
    approval_secret: str = "change-me-in-dotenv"
    approval_ttl_seconds: int = 600
    owner_demo_token: str = "demo-owner-token"  # replace with real auth after the competition
    sandbox_mode: bool = True  # never turn off for the competition

    # Demo
    demo_account_id: str = "ACC-SAMPLE-CAFE"
    cors_origins: list[str] = ["http://localhost:3000"]

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]

    @property
    def llm_extra_body_dict(self) -> dict:
        return json.loads(self.llm_extra_body) if self.llm_extra_body.strip() else {}


settings = Settings()
