from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from .models import DataSnapshot, Document, SnapshotMember


class SnapshotImmutableError(RuntimeError):
    pass


class Repository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_document(self, **values: object) -> Document:
        existing = self.session.scalar(
            select(Document).where(Document.accession_number == values["accession_number"])
        )
        if existing:
            if existing.content_hash != values["content_hash"]:
                raise ValueError("content hash conflict for document natural key")
            return existing
        document = Document(**values)
        self.session.add(document)
        self.session.flush()
        return document

    def add_snapshot_member(
        self, snapshot_id: int, record_type: str, record_id: str, content_hash: str
    ) -> None:
        snapshot = self.session.get(DataSnapshot, snapshot_id)
        if snapshot is None:
            raise LookupError("snapshot not found")
        if snapshot.frozen_at is not None:
            raise SnapshotImmutableError("snapshot is frozen")
        self.session.add(
            SnapshotMember(
                snapshot_id=snapshot_id,
                record_type=record_type,
                record_id=record_id,
                content_hash=content_hash,
            )
        )

    _MEMBER_BATCH = 10000

    def create_snapshot(self, name: str, members: list[tuple[str, str, str]]) -> DataSnapshot:
        manifest = sorted(members)
        # Stream the manifest digest instead of materializing one large JSON
        # string: a multi-million-member run otherwise builds a several-hundred-MB
        # string and OOM-kills the 8 GB batch container (ADR-009). The byte
        # sequence matches ``json.dumps(manifest, separators=(",", ":"))``.
        hasher = hashlib.sha256()
        hasher.update(b"[")
        counts: dict[str, int] = {}
        for index, member in enumerate(manifest):
            if index:
                hasher.update(b",")
            hasher.update(json.dumps(list(member), separators=(",", ":")).encode())
            counts[member[0]] = counts.get(member[0], 0) + 1
        hasher.update(b"]")
        digest = hasher.hexdigest()
        by_name = self.session.scalar(select(DataSnapshot).where(DataSnapshot.name == name))
        if by_name:
            if by_name.manifest_hash != digest:
                raise SnapshotImmutableError(
                    "snapshot name already identifies a different manifest"
                )
            return by_name
        existing = self.session.scalar(
            select(DataSnapshot).where(DataSnapshot.manifest_hash == digest)
        )
        if existing:
            return existing
        # Store a compact summary rather than the full member list: nothing reads
        # the list back, the SnapshotMember rows are the source of truth, and
        # manifest_hash provides immutability (RW-FR-015).
        snapshot = DataSnapshot(
            name=name,
            manifest_hash=digest,
            manifest_json={"member_count": len(manifest), "counts_by_type": counts},
        )
        self.session.add(snapshot)
        self.session.flush()
        # Bulk-insert members in batches instead of adding millions of ORM
        # instances to the identity map at once (ADR-009).
        batch: list[dict[str, object]] = []
        for record_type, record_id, content_hash in manifest:
            batch.append(
                {
                    "snapshot_id": snapshot.id,
                    "record_type": record_type,
                    "record_id": record_id,
                    "content_hash": content_hash,
                }
            )
            if len(batch) >= self._MEMBER_BATCH:
                self.session.execute(insert(SnapshotMember), batch)
                batch.clear()
        if batch:
            self.session.execute(insert(SnapshotMember), batch)
        snapshot.frozen_at = datetime.now(UTC)
        self.session.flush()
        return snapshot
