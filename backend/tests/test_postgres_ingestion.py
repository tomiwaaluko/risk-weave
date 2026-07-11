from __future__ import annotations

import os
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError


@pytest.mark.skipif(
    not os.environ.get("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL is required for PostgreSQL migration integration tests",
)
def test_postgres_snapshot_is_immutable() -> None:
    engine = create_engine(os.environ["TEST_DATABASE_URL"])
    with engine.begin() as connection:
        frozen_id = connection.scalar(
            text(
                """
                INSERT INTO data_snapshots (name, manifest_hash, frozen_at, manifest_json)
                VALUES ('frozen', 'frozen-hash', NULL, '{}') RETURNING id
                """
            )
        )
        member_id = connection.scalar(
            text(
                """
                INSERT INTO snapshot_members (snapshot_id, record_type, record_id, content_hash)
                VALUES (:snapshot_id, 'document', 'doc-1', 'hash-1') RETURNING id
                """
            ),
            {"snapshot_id": frozen_id},
        )
        connection.execute(
            text("UPDATE data_snapshots SET frozen_at = :now WHERE id = :snapshot_id"),
            {"now": datetime.now(UTC), "snapshot_id": frozen_id},
        )
        mutable_id = connection.scalar(
            text(
                """
                INSERT INTO data_snapshots (name, manifest_hash, frozen_at, manifest_json)
                VALUES ('mutable', 'mutable-hash', NULL, '{}') RETURNING id
                """
            )
        )
        mutable_member_id = connection.scalar(
            text(
                """
                INSERT INTO snapshot_members (snapshot_id, record_type, record_id, content_hash)
                VALUES (:snapshot_id, 'document', 'doc-2', 'hash-2') RETURNING id
                """
            ),
            {"snapshot_id": mutable_id},
        )

    statements = [
        (
            "INSERT INTO snapshot_members "
            "(snapshot_id, record_type, record_id, content_hash) "
            "VALUES (:frozen_id, 'document', 'doc-3', 'hash-3')",
            {"frozen_id": frozen_id},
        ),
        (
            "UPDATE snapshot_members SET content_hash = 'changed' WHERE id = :member_id",
            {"member_id": member_id},
        ),
        ("DELETE FROM snapshot_members WHERE id = :member_id", {"member_id": member_id}),
        (
            "UPDATE snapshot_members SET snapshot_id = :frozen_id WHERE id = :mutable_member_id",
            {"frozen_id": frozen_id, "mutable_member_id": mutable_member_id},
        ),
        (
            "UPDATE data_snapshots SET manifest_json = '{\"changed\": true}' WHERE id = :frozen_id",
            {"frozen_id": frozen_id},
        ),
        ("DELETE FROM data_snapshots WHERE id = :frozen_id", {"frozen_id": frozen_id}),
    ]
    for statement, parameters in statements:
        with engine.begin() as connection, pytest.raises(DBAPIError, match="snapshot is immutable"):
            connection.execute(text(statement), parameters)
