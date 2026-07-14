from pydantic import SecretStr
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
