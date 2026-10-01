"""Run snapshot extraction and stop when recorded Gemini spend exceeds $18.

The dollar figure is the registered Flash price in ``riskweave.accounting.pricing``,
the same meter as ``GET /accounting/gemini/budget``. Each chunk is committed
before the next call so a stop persists and a later run resumes.
"""

from __future__ import annotations

import os
import urllib.error
from datetime import UTC, datetime
from decimal import Decimal

from riskweave_api.accounting.service import BudgetExceededError, GeminiAccountingService
from riskweave_api.extraction.gemini import GeminiExtractionClient, GeminiResponseError
from riskweave_api.extraction.service import ExtractionService, OffsetMismatchError
from riskweave_api.ingestion.database import session_factory
from riskweave_api.settings import Settings

SPEND_CAP_USD = Decimal("18")


def should_stop(spent_usd: Decimal, cap_usd: Decimal = SPEND_CAP_USD) -> bool:
    return spent_usd > cap_usd


def main(argv: list[str] | None = None) -> int:
    del argv
    settings = Settings()
    cap = Decimal(os.environ.get("GEMINI_EXTRACTION_SPEND_CAP_USD", str(SPEND_CAP_USD)))
    snapshot_id = int(os.environ.get("EXTRACTION_SNAPSHOT_ID", "3"))
    accounting = GeminiAccountingService(
        soft_daily_budget_usd=min(Decimal(str(settings.gemini_daily_soft_budget_usd)), cap),
        hard_daily_budget_usd=cap,
    )
    factory = session_factory(settings.database_url)
    client = GeminiExtractionClient.from_settings(settings)

    with factory() as session:
        chunk_ids = ExtractionService(session, client, accounting)._snapshot_chunk_ids(snapshot_id)
    print(f"snapshot_id={snapshot_id} chunks={len(chunk_ids)} cap_usd={cap}", flush=True)

    for index, chunk_id in enumerate(chunk_ids, start=1):
        relationship_inserted = _extract_one(
            factory, accounting, client, snapshot_id, chunk_id, "relationships", cap
        )
        if relationship_inserted is None:
            return 0
        covenant_inserted = _extract_one(
            factory, accounting, client, snapshot_id, chunk_id, "covenants", cap
        )
        if covenant_inserted is None:
            return 0
        print(
            f"chunk {index}/{len(chunk_ids)} id={chunk_id} "
            f"relationships={relationship_inserted} covenants={covenant_inserted}",
            flush=True,
        )
    print("extraction finished under cap", flush=True)
    return 0


def _extract_one(factory, accounting, client, snapshot_id, chunk_id, kind, cap) -> int | None:
    with factory() as session:
        spent = accounting.daily_spend_usd(session, datetime.now(UTC).date())
        if should_stop(spent, cap):
            print(f"stop: spent_usd={spent} above cap_usd={cap}", flush=True)
            return None
        service = ExtractionService(session, client, accounting)
        try:
            if kind == "relationships":
                result = service.extract_relationships_for_chunk(snapshot_id, chunk_id)
            else:
                result = service.extract_covenants_for_chunk(snapshot_id, chunk_id)
        except BudgetExceededError as exc:
            session.rollback()
            print(f"stop: {exc}", flush=True)
            return None
        except GeminiResponseError as exc:
            session.commit()
            print(f"chunk_id={chunk_id} {kind} schema_invalid: {exc}", flush=True)
            return 0
        except (TimeoutError, urllib.error.URLError) as exc:
            session.rollback()
            print(f"chunk_id={chunk_id} {kind} transport_error: {exc}", flush=True)
            return 0
        except OffsetMismatchError as exc:
            session.commit()
            print(f"chunk_id={chunk_id} {kind} offset_mismatch: {exc}", flush=True)
            return 0
        except Exception as exc:
            session.rollback()
            print(f"chunk_id={chunk_id} {kind} skipped_after_error: {exc}", flush=True)
            return 0
        session.commit()
        spent = accounting.daily_spend_usd(session, datetime.now(UTC).date())
        print(
            f"chunk_id={chunk_id} {kind} inserted={result.inserted} spent_usd={spent}",
            flush=True,
        )
        if should_stop(spent, cap):
            print(f"stop: spent_usd={spent} above cap_usd={cap}", flush=True)
            return None
        return result.inserted


if __name__ == "__main__":
    raise SystemExit(main())
