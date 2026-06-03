"""Local JSONL and SQLite storage for pipeline records."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from crawler.models import SerializableRecord


SCHEMA_VERSION = 1


def append_jsonl(path: str | Path, records: Iterable[SerializableRecord]) -> int:
    """Append records to a JSONL file and return the number written."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with target.open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(record.to_json())
            handle.write("\n")
            count += 1
    return count


def read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    """Read JSONL records as dictionaries."""
    source = Path(path)
    if not source.exists():
        return []
    records: list[dict[str, Any]] = []
    with source.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as error:
                raise ValueError(f"invalid JSONL at line {line_number}: {error}") from error
    return records


def initialize_sqlite(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite database and ensure the local storage schema exists."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS records (
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            source_id TEXT,
            document_id TEXT,
            claim_id TEXT,
            url TEXT,
            checksum TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (record_type, record_id)
        )
        """,
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_records_document_id
        ON records(document_id)
        """,
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_records_url_checksum
        ON records(url, checksum)
        """,
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_info (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
    )
    connection.execute(
        """
        INSERT OR REPLACE INTO schema_info(key, value)
        VALUES ('schema_version', ?)
        """,
        (str(SCHEMA_VERSION),),
    )
    connection.commit()
    return connection


def upsert_record(
    connection: sqlite3.Connection,
    record: SerializableRecord,
    *,
    created_at: str | None = None,
) -> None:
    """Insert or replace one pipeline record in SQLite."""
    payload = record.to_dict()
    connection.execute(
        """
        INSERT OR REPLACE INTO records (
            record_type,
            record_id,
            source_id,
            document_id,
            claim_id,
            url,
            checksum,
            payload_json,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            type(record).__name__,
            record_id(payload),
            payload.get("source_id"),
            payload.get("document_id"),
            payload.get("claim_id"),
            payload.get("url"),
            payload.get("checksum"),
            json.dumps(payload, sort_keys=True),
            created_at or datetime.now(UTC).isoformat(),
        ),
    )


def upsert_records(
    connection: sqlite3.Connection,
    records: Iterable[SerializableRecord],
    *,
    created_at: str | None = None,
) -> int:
    """Insert or replace many pipeline records and return the count."""
    count = 0
    for record in records:
        upsert_record(connection, record, created_at=created_at)
        count += 1
    connection.commit()
    return count


def fetch_records(
    connection: sqlite3.Connection,
    record_type: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch stored record payloads, optionally filtered by record type."""
    if record_type is None:
        cursor = connection.execute(
            "SELECT payload_json FROM records ORDER BY record_type, record_id",
        )
    else:
        cursor = connection.execute(
            """
            SELECT payload_json
            FROM records
            WHERE record_type = ?
            ORDER BY record_id
            """,
            (record_type,),
        )
    return [json.loads(row[0]) for row in cursor.fetchall()]


def find_documents_by_url_checksum(
    connection: sqlite3.Connection,
    *,
    url: str,
    checksum: str,
) -> list[dict[str, Any]]:
    """Find fetched documents matching a URL and checksum."""
    cursor = connection.execute(
        """
        SELECT payload_json
        FROM records
        WHERE record_type = 'FetchedDocument'
          AND url = ?
          AND checksum = ?
        ORDER BY record_id
        """,
        (url, checksum),
    )
    return [json.loads(row[0]) for row in cursor.fetchall()]


def storage_log_entry(
    *,
    destination: str,
    record_count: int,
    storage_type: str,
) -> dict[str, object]:
    """Create a structured log entry for storage writes."""
    return {
        "stage": "store_records",
        "storage_type": storage_type,
        "destination": destination,
        "record_count": record_count,
    }


def record_id(payload: dict[str, Any]) -> str:
    """Return the canonical ID field for a serialized record payload."""
    for key in (
        "source_id",
        "run_id",
        "item_id",
        "document_id",
        "entity_id",
        "claim_id",
    ):
        value = payload.get(key)
        if value:
            return str(value)
    raise ValueError(f"record has no stable ID field: {sorted(payload)}")
