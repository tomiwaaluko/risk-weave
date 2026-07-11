from pathlib import Path

import pytest
from pydantic import ValidationError

from riskweave_api.settings import Settings


def test_settings_reject_missing_infrastructure_configuration(monkeypatch) -> None:
    for variable in (
        "DATABASE_URL",
        "NEO4J_URI",
        "NEO4J_USER",
        "NEO4J_PASSWORD",
        "REDIS_URL",
        "GEMINI_API_KEY",
    ):
        monkeypatch.delenv(variable, raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_accept_server_side_configuration() -> None:
    settings = Settings(
        database_url="postgresql://riskweave:password@postgres:5432/riskweave",
        neo4j_uri="bolt://neo4j:7687",
        neo4j_user="neo4j",
        neo4j_password="password",
        redis_url="redis://redis:6379/0",
        gemini_api_key="test-placeholder",
    )

    assert settings.neo4j_user == "neo4j"


def test_example_environment_defines_required_server_settings() -> None:
    example_environment = Path(__file__).parents[2] / ".env.example"

    settings = Settings(_env_file=example_environment)

    assert settings.database_url.startswith("postgresql://")
