"""Print what snapshot extraction already saved. Does not call Gemini."""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text

QUERIES = (
    "select count(*) from relationship_extractions",
    "select count(*) from covenant_threshold_extractions",
    "select status, count(*) from extraction_runs group by status order by status",
    "select count(*), coalesce(sum(cost_usd), 0) from gemini_usage_records",
    "select purpose, count(*), coalesce(sum(cost_usd), 0) from gemini_usage_records group by purpose order by purpose",
    "select relationship_type, count(*) from relationship_extractions group by relationship_type order by count(*) desc",
    "select count(distinct chunk_id) from relationship_extractions",
    "select count(distinct chunk_id) from extraction_runs where status = 'completed'",
    "select source_entity, target_entity, relationship_type, direction, disclosed_magnitude, left(source_passage, 300), source_document_id, extraction_confidence from relationship_extractions",
    "select left(outcome_json::text, 500) from extraction_runs where status = 'schema_invalid' limit 3",
)


def main() -> int:
    database_url = os.environ["DATABASE_URL"].replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(database_url, pool_pre_ping=True)
    with engine.connect() as connection:
        for query in QUERIES:
            rows = connection.execute(text(query)).all()
            print(query, flush=True)
            for row in rows:
                print(" ", row, flush=True)
    print("saved_report_done", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
