from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
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

    def create_snapshot(self, name: str, members: list[tuple[str, str, str]]) -> DataSnapshot:
        manifest = sorted(members)
        digest = hashlib.sha256(json.dumps(manifest, separators=(",", ":")).encode()).hexdigest()
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
        snapshot = DataSnapshot(
            name=name, manifest_hash=digest, manifest_json={"members": manifest}
        )
        self.session.add(snapshot)
        self.session.flush()
        for record_type, record_id, content_hash in manifest:
            self.add_snapshot_member(snapshot.id, record_type, record_id, content_hash)
        self.session.flush()
        snapshot.frozen_at = datetime.now(UTC)
        self.session.flush()
        return snapshot
