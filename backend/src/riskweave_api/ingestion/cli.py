from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from alembic.config import Config

from alembic import command

from .clients import FredClient, ProviderError, SecClient
from .database import session_factory
from .service import IngestionService

REPO_ROOT = Path(__file__).resolve().parents[4]


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RiskWeave pre-demo batch ingestion")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "data/universe/entities.json")
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL")
    fred_key = os.environ.get("FRED_API_KEY")
    sec_user_agent = os.environ.get("SEC_USER_AGENT")
    if not database_url or not fred_key or not sec_user_agent:
        parser.error("DATABASE_URL, FRED_API_KEY, and SEC_USER_AGENT are required")
    alembic_ini = os.environ.get(
        "RISKWEAVE_ALEMBIC_INI", str(REPO_ROOT / "backend/alembic.ini")
    )
    config = Config(alembic_ini)
    config.set_main_option(
        "sqlalchemy.url", database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    command.upgrade(config, "head")
    try:
        with session_factory(database_url)() as session:
            result = IngestionService(session, SecClient(sec_user_agent), FredClient(fred_key)).run(
                args.universe, args.snapshot
            )
    except ProviderError as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
