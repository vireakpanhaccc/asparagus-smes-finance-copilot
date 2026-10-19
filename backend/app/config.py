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

    # Security. No defaults: the API refuses to start until both are set (see insecure_settings).
    approval_secret: str = ""
    approval_ttl_seconds: int = 600
    owner_demo_token: str = ""  # replace with real auth after the competition
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

    def insecure_settings(self) -> list[str]:
        """Secrets that are missing, too short or a published default. Empty list = OK."""
        problems = []
        for name, value, min_len in (("APPROVAL_SECRET", self.approval_secret, 32),
                                     ("OWNER_DEMO_TOKEN", self.owner_demo_token, 16)):
            if not value:
                problems.append(f"{name} is not set")
            elif value in KNOWN_DEFAULTS:
                problems.append(f"{name} is a published default")
            elif len(value) < min_len:
                problems.append(f"{name} is shorter than {min_len} characters")
        return problems


# Values that have appeared in this repository; anyone can read them.
KNOWN_DEFAULTS = {"change-me", "change-me-in-dotenv", "demo-owner-token"}


settings = Settings()
