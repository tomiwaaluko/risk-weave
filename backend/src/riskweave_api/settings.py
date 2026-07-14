from typing import Literal

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server-only infrastructure configuration."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: SecretStr
    redis_url: str
    gemini_api_key: SecretStr
    fred_api_key: SecretStr | None = None
    sec_user_agent: str = "RiskWeave contact@example.com"
    cors_allow_origin_regex: str = r"^https://riskweave.*\.vercel\.app$|^http://localhost:3000$"
    # RIS-30: which ScenarioStore implementation the API lifespan constructs.
    # Defaults to the in-memory fixture/test/offline-demo backend; Railway
    # (ADR-008) sets this to "postgres" so scenarios/runs survive restarts.
    scenario_store_backend: Literal["memory", "postgres"] = "memory"

    # RIS-31 / ADR-010: unset (local dev, CI, Docker Compose) leaves the API
    # open, matching today's behavior. Railway production always sets this.
    api_key: SecretStr | None = Field(default=None, validation_alias="RISKWEAVE_API_KEY")
    rate_limit_enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")
