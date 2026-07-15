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
    # Matches the project's Vercel origins (production alias + git/preview
    # subdomains, all under the ``risk-weave`` prefix) and local dev. The
    # subdomain body is restricted to Vercel hostname characters rather than
    # ``.*`` so the allowlist can't be widened by a stray path or scheme.
    cors_allow_origin_regex: str = (
        r"^https://risk-weave[a-z0-9-]*\.vercel\.app$|^http://localhost:3000$"
    )
    # RIS-30: which ScenarioStore implementation the API lifespan constructs.
    # Defaults to the in-memory fixture/test/offline-demo backend; Railway
    # (ADR-008) sets this to "postgres" so scenarios/runs survive restarts.
    scenario_store_backend: Literal["memory", "postgres"] = "memory"

    # RIS-31 / ADR-010: unset (local dev, CI, Docker Compose) leaves the API
    # open, matching today's behavior. Railway production always sets this.
    api_key: SecretStr | None = Field(default=None, validation_alias="RISKWEAVE_API_KEY")
    rate_limit_enabled: bool = Field(default=True, validation_alias="RATE_LIMIT_ENABLED")

    # RIS-34: Gemini daily spend thresholds (`RW-AI-003`, spec §15). The soft
    # threshold only logs a warning; the hard threshold refuses further
    # extraction-batch calls (resumable — see GeminiAccountingService) while
    # leaving interactive parse/explanation/Q&A open, per the spec's decision
    # priority (reliable demo behavior over cost, §0.4). Hackathon-scale
    # defaults; tune per the RIS-28 batch cost estimate before a full run.
    gemini_daily_soft_budget_usd: float = Field(
        default=5.0, validation_alias="GEMINI_DAILY_SOFT_BUDGET_USD"
    )
    gemini_daily_hard_budget_usd: float = Field(
        default=20.0, validation_alias="GEMINI_DAILY_HARD_BUDGET_USD"
    )

    # RIS-34 / RW-DATA-005: documented provider fair-use ceilings the ingestion
    # pipeline asserts its measured request counts against. SEC EDGAR's fair
    # access policy caps automated traffic at 10 requests/second (already
    # enforced by SecClient's RateLimiter); FRED's API terms cap a single key
    # at 120 requests/minute. An attempt to re-verify both live via WebFetch on
    # 2026-07-15 failed with HTTP 403 from each host; these are the last-known
    # documented values pending a re-check with direct network access.
    sec_fair_use_requests_per_second: int = Field(
        default=10, validation_alias="SEC_FAIR_USE_REQUESTS_PER_SECOND"
    )
    fred_rate_limit_requests_per_minute: int = Field(
        default=120, validation_alias="FRED_RATE_LIMIT_REQUESTS_PER_MINUTE"
    )
