from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .canonicalize import canonicalize_filing_html
from .catalog import FRED_SERIES
from .chunking import chunk_text
from .clients import FredClient, SecClient
from .models import (
    Document,
    DocumentChunk,
    IngestionRun,
    MacroObservation,
    MacroSeries,
    XbrlFact,
)
from .repository import Repository

logger = logging.getLogger("riskweave_api.ingestion")


def _hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


class IngestionService:
    def __init__(self, session: Session, sec: SecClient, fred: FredClient) -> None:
        self.session = session
        self.sec = sec
        self.fred = fred
        self.repository = Repository(session)

    def run(self, universe_path: Path, snapshot_name: str) -> dict[str, object]:
        # No cross-run lock: concurrent runs are prevented by the single-replica,
        # deploy-triggered one-off job model, and correctness under any overlap is
        # guaranteed by idempotent content-hash / accession upserts (RW-FR-014). A
        # database advisory lock was tried (ADR-009) but leaked across pooled
        # connections and wedged every subsequent run, so it was removed.
        run = IngestionRun(started_at=datetime.now(UTC), status="running", metadata_json={})
        self.session.add(run)
        self.session.commit()
        run_id = run.id
        try:
            entities = json.loads(universe_path.read_text(encoding="utf-8"))["entities"]
            ciks = sorted({entity["cik"] for entity in entities if entity.get("cik")})
            members: list[tuple[str, str, str]] = []
            # Commit and expunge after each provider unit so filings, chunks, and
            # XBRL facts do not accumulate in the identity map across the whole
            # universe. Holding the entire run in one transaction grew memory
            # monotonically and OOM-killed the 8 GB batch container (ADR-009).
            # ``members`` holds only small identity tuples.
            logger.info("ingesting SEC filings and XBRL facts for %d CIKs", len(ciks))
            for index, cik in enumerate(ciks, start=1):
                members.extend(self._ingest_sec(cik))
                self.session.commit()
                self.session.expunge_all()
                logger.info("SEC %d/%d cik=%s members=%d", index, len(ciks), cik, len(members))
            logger.info("ingesting %d FRED series", len(FRED_SERIES))
            for series_id in FRED_SERIES:
                members.extend(self._ingest_fred(series_id))
                self.session.commit()
                self.session.expunge_all()
                logger.info("FRED series=%s members=%d", series_id, len(members))
            snapshot = self.repository.create_snapshot(snapshot_name, members)
            snapshot_id = snapshot.id
            manifest_hash = snapshot.manifest_hash
            counts = {
                "documents": self._count(Document),
                "document_chunks": self._count(DocumentChunk),
                "xbrl_facts": self._count(XbrlFact),
                "macro_series": self._count(MacroSeries),
                "macro_observations": self._count(MacroObservation),
            }
            run = self.session.get(IngestionRun, run_id)
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            run.metadata_json = {
                "members": len(members),
                "snapshot_id": snapshot_id,
                "counts": counts,
            }
            self.session.commit()
            return {
                "snapshot_id": snapshot_id,
                "manifest_hash": manifest_hash,
                "members": len(members),
                "counts": counts,
            }
        except Exception:
            self.session.rollback()
            failed_run = self.session.get(IngestionRun, run_id)
            if failed_run:
                failed_run.status = "failed"
                failed_run.completed_at = datetime.now(UTC)
                self.session.commit()
            raise

    def _count(self, model: type) -> int:
        return self.session.scalar(select(func.count()).select_from(model)) or 0

    @staticmethod
    def _rows(columns: dict[str, list[object]]) -> list[dict[str, object]]:
        count = max(
            (len(value) for value in columns.values() if isinstance(value, list)), default=0
        )
        return [
            {key: values[index] for key, values in columns.items() if index < len(values)}
            for index in range(count)
        ]

    def _ingest_sec(self, cik: str) -> list[tuple[str, str, str]]:
        retrieved_at = datetime.now(UTC)
        members: list[tuple[str, str, str]] = []
        existing_documents = {
            accession: content_hash
            for accession, content_hash in self.session.execute(
                select(Document.accession_number, Document.content_hash).where(Document.cik == cik)
            )
        }
        submissions = self.sec.submissions(cik)
        filings = submissions.get("filings", {})
        filing_rows = self._rows(filings.get("recent", {}))
        counts = {
            form: sum(row.get("form") == form for row in filing_rows)
            for form in ("10-K", "10-Q", "8-K")
        }
        for file_entry in filings.get("files", []):
            if all(count >= 3 for count in counts.values()):
                break
            older_rows = self._rows(self.sec.submissions_file(file_entry["name"]))
            filing_rows.extend(older_rows)
            for form in counts:
                counts[form] += sum(row.get("form") == form for row in older_rows)
        selected: dict[str, int] = {form: 0 for form in ("10-K", "10-Q", "8-K")}
        for filing in filing_rows:
            form = filing.get("form")
            if form not in selected or selected[form] >= 3:
                continue
            accession = str(filing["accessionNumber"])
            if accession in existing_documents:
                members.append(("document", accession, existing_documents[accession]))
                selected[form] += 1
                continue
            primary_document = str(filing["primaryDocument"])
            url, raw_html = self.sec.filing(cik, accession, primary_document)
            canonical = canonicalize_filing_html(raw_html)
            document = self.repository.upsert_document(
                source_document_id=accession,
                cik=cik,
                accession_number=accession,
                form=form,
                filing_date=date.fromisoformat(str(filing["filingDate"])),
                source_url=url,
                retrieved_at=retrieved_at,
                content_hash=hashlib.sha256(canonical.encode()).hexdigest(),
                canonical_text=canonical,
                provider_metadata=filing,
                normalization_map={"strategy": "canonical-html-v1"},
            )
            if not document.chunks:
                for ordinal, chunk in enumerate(chunk_text(canonical)):
                    document.chunks.append(
                        DocumentChunk(
                            ordinal=ordinal,
                            text=chunk.text,
                            char_start=chunk.char_start,
                            char_end=chunk.char_end,
                            overlap_start=chunk.overlap_start,
                            overlap_end=chunk.overlap_end,
                            content_hash=hashlib.sha256(chunk.text.encode()).hexdigest(),
                        )
                    )
            members.append(("document", accession, document.content_hash))
            selected[form] += 1
        facts = self.sec.companyfacts(cik).get("facts", {})
        existing_facts = {
            identity_hash: content_hash
            for identity_hash, content_hash in self.session.execute(
                select(XbrlFact.identity_hash, XbrlFact.content_hash).where(XbrlFact.cik == cik)
            )
        }
        for taxonomy, concepts in facts.items():
            for concept, detail in concepts.items():
                for unit, rows in detail.get("units", {}).items():
                    for row in rows:
                        if row.get("form") not in {"10-K", "10-Q", "8-K"} or not row.get("accn"):
                            continue
                        identity = {
                            key: row.get(key)
                            for key in ("start", "end", "accn", "form", "fy", "fp", "frame")
                        } | {"cik": cik, "taxonomy": taxonomy, "concept": concept, "unit": unit}
                        identity_hash = _hash(identity)
                        content_hash = _hash(row)
                        if identity_hash in existing_facts:
                            if existing_facts[identity_hash] != content_hash:
                                raise ValueError("content hash conflict for XBRL fact")
                            members.append(("xbrl_fact", identity_hash, content_hash))
                            continue
                        self.session.add(
                            XbrlFact(
                                identity_hash=identity_hash,
                                cik=cik,
                                taxonomy=taxonomy,
                                concept=concept,
                                unit=unit,
                                value=str(row.get("val")),
                                start_date=date.fromisoformat(row["start"])
                                if row.get("start")
                                else None,
                                end_date=date.fromisoformat(row["end"]),
                                accession_number=row["accn"],
                                form=row["form"],
                                filed_date=date.fromisoformat(row["filed"]),
                                fiscal_year=row.get("fy"),
                                fiscal_period=row.get("fp"),
                                frame=row.get("frame"),
                                retrieved_at=retrieved_at,
                                content_hash=content_hash,
                            )
                        )
                        existing_facts[identity_hash] = content_hash
                        members.append(("xbrl_fact", identity_hash, content_hash))
        return members

    def _ingest_fred(self, series_id: str) -> list[tuple[str, str, str]]:
        retrieved_at = datetime.now(UTC)
        members: list[tuple[str, str, str]] = []
        series_row = self.fred.series(series_id).get("seriess", [])[0]
        series_hash = _hash(series_row)
        series = self.session.get(MacroSeries, series_id)
        if series is None:
            series = MacroSeries(
                series_id=series_id,
                title=series_row["title"],
                units=series_row["units"],
                frequency=series_row["frequency"],
                source_release=series_row.get("notes"),
                retrieved_at=retrieved_at,
                metadata_json=series_row,
                content_hash=series_hash,
            )
            self.session.add(series)
        elif series.content_hash != series_hash:
            raise ValueError("content hash conflict for macro series")
        members.append(("macro_series", series_id, series_hash))
        observation_rows = self.session.execute(
            select(
                MacroObservation.observation_date,
                MacroObservation.realtime_start,
                MacroObservation.realtime_end,
                MacroObservation.content_hash,
            ).where(MacroObservation.series_id == series_id)
        )
        existing_observations = {
            observation_date: content_hash
            for observation_date, _realtime_start, _realtime_end, content_hash in observation_rows
        }
        for row in self.fred.observations(series_id).get("observations", []):
            if row["value"] == ".":
                continue
            observation_date = date.fromisoformat(row["date"])
            realtime_start = date.fromisoformat(row["realtime_start"])
            realtime_end = date.fromisoformat(row["realtime_end"])
            identity = observation_date
            content_hash = _hash({"date": row["date"], "value": row["value"]})
            record_id = f"{series_id}:{row['date']}"
            if identity in existing_observations:
                if existing_observations[identity] != content_hash:
                    raise ValueError("content hash conflict for macro observation")
                members.append(("macro_observation", record_id, content_hash))
                continue
            try:
                value = Decimal(row["value"])
            except InvalidOperation as exc:
                raise ValueError("invalid FRED observation value") from exc
            self.session.add(
                MacroObservation(
                    series_id=series_id,
                    observation_date=observation_date,
                    value=value,
                    realtime_start=realtime_start,
                    realtime_end=realtime_end,
                    retrieved_at=retrieved_at,
                    content_hash=content_hash,
                )
            )
            existing_observations[identity] = content_hash
            members.append(("macro_observation", record_id, content_hash))
        return members
