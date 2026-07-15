from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

from alembic.config import Config

from alembic import command

from .clients import FredClient, ProviderError, SecClient
from .database import session_factory
from .service import IngestionService

REPO_ROOT = Path(__file__).resolve().parents[4]

logger = logging.getLogger("riskweave_api.ingestion")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the RiskWeave pre-demo batch ingestion")
    parser.add_argument("--snapshot", required=True)
    parser.add_argument("--universe", type=Path, default=REPO_ROOT / "data/universe/entities.json")
    args = parser.parse_args()
    # Log to stderr so batch progress is visible in the platform log stream even
    # for short-lived one-off containers whose final stdout line can be dropped
    # on teardown; the machine-readable summary still goes to stdout.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    database_url = os.environ.get("DATABASE_URL")
    fred_key = os.environ.get("FRED_API_KEY")
    sec_user_agent = os.environ.get("SEC_USER_AGENT")
    if not database_url or not fred_key or not sec_user_agent:
        parser.error("DATABASE_URL, FRED_API_KEY, and SEC_USER_AGENT are required")
    sec_fair_use_rps = int(os.environ.get("SEC_FAIR_USE_REQUESTS_PER_SECOND", "10"))
    fred_rate_limit_rpm = int(os.environ.get("FRED_RATE_LIMIT_REQUESTS_PER_MINUTE", "120"))
    alembic_ini = os.environ.get("RISKWEAVE_ALEMBIC_INI", str(REPO_ROOT / "backend/alembic.ini"))
    config = Config(alembic_ini)
    config.set_main_option(
        "sqlalchemy.url", database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    )
    logger.info("applying database migrations")
    command.upgrade(config, "head")
    logger.info("starting ingestion snapshot=%s universe=%s", args.snapshot, args.universe)
    started = time.monotonic()
    try:
        with session_factory(database_url)() as session:
            sec_client = SecClient(sec_user_agent, fair_use_requests_per_second=sec_fair_use_rps)
            fred_client = FredClient(fred_key, rate_limit_requests_per_minute=fred_rate_limit_rpm)
            result = IngestionService(session, sec_client, fred_client).run(
                args.universe, args.snapshot
            )
    except ProviderError as exc:
        parser.error(str(exc))
    duration_seconds = round(time.monotonic() - started, 1)
    logger.info(
        "ingestion complete duration_seconds=%s %s",
        duration_seconds,
        json.dumps(result, sort_keys=True),
    )
    print(json.dumps({**result, "duration_seconds": duration_seconds}, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
