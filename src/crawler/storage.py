"""Local JSONL and SQLite storage helpers.

The project starts with simple durable storage so every stage can be inspected
without a production database. JSONL gives transparent audit artifacts, while
SQLite supports local structured lookup and duplicate checks.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import json
from pathlib import Path
import sqlite3
from typing import Any

from crawler.models import SerializableRecord


SCHEMA_VERSION = 2


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
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS run_summaries (
            run_id TEXT PRIMARY KEY,
            status TEXT,
            started_at TEXT,
            finished_at TEXT,
            output_dir TEXT,
            summary_json TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS run_records (
            run_id TEXT NOT NULL,
            record_name TEXT NOT NULL,
            record_type TEXT NOT NULL,
            record_id TEXT NOT NULL,
            source_id TEXT,
            document_id TEXT,
            claim_id TEXT,
            url TEXT,
            checksum TEXT,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            PRIMARY KEY (run_id, record_name, record_id)
        )
        """,
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_records_lookup
        ON run_records(run_id, record_name)
        """,
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_run_records_claim
        ON run_records(run_id, claim_id)
        """,
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS run_artifacts (
            run_id TEXT NOT NULL,
            artifact_path TEXT NOT NULL,
            artifact_type TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (run_id, artifact_path)
        )
        """,
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS audit_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            run_id TEXT,
            claim_id TEXT,
            document_id TEXT,
            source_id TEXT,
            payload_json TEXT NOT NULL
        )
        """,
    )
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_audit_events_run
        ON audit_events(run_id, created_at)
        """,
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


def upsert_run_summary(
    connection: sqlite3.Connection,
    summary: dict[str, Any],
    *,
    updated_at: str | None = None,
) -> None:
    """Insert or replace one run summary in durable storage."""

    run_id = str(summary.get("run_id") or "").strip()
    if not run_id:
        raise ValueError("run summary requires run_id")
    timestamp = updated_at or datetime.now(UTC).isoformat()
    connection.execute(
        """
        INSERT OR REPLACE INTO run_summaries (
            run_id,
            status,
            started_at,
            finished_at,
            output_dir,
            summary_json,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            summary.get("status"),
            summary.get("started_at"),
            summary.get("finished_at"),
            summary.get("output_dir"),
            json.dumps(summary, sort_keys=True),
            timestamp,
        ),
    )
    connection.commit()


def fetch_run_summary(
    connection: sqlite3.Connection,
    run_id: str,
) -> dict[str, Any] | None:
    """Fetch one run summary from durable storage."""

    row = connection.execute(
        "SELECT summary_json FROM run_summaries WHERE run_id = ?",
        (run_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def list_run_summaries(connection: sqlite3.Connection) -> list[dict[str, Any]]:
    """List run summaries from durable storage."""

    rows = connection.execute(
        """
        SELECT summary_json
        FROM run_summaries
        ORDER BY COALESCE(finished_at, started_at, updated_at) DESC, run_id
        """,
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def upsert_run_records(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    record_name: str,
    records: Iterable[dict[str, Any] | SerializableRecord],
    created_at: str | None = None,
) -> int:
    """Insert or replace records scoped to one crawler run."""

    timestamp = created_at or datetime.now(UTC).isoformat()
    count = 0
    for record in records:
        payload = record.to_dict() if isinstance(record, SerializableRecord) else record
        payload = dict(payload)
        connection.execute(
            """
            INSERT OR REPLACE INTO run_records (
                run_id,
                record_name,
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
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                record_name,
                _record_type_for_name(record_name),
                record_id(payload),
                payload.get("source_id"),
                payload.get("document_id"),
                payload.get("claim_id"),
                payload.get("url"),
                payload.get("checksum"),
                json.dumps(payload, sort_keys=True),
                timestamp,
            ),
        )
        count += 1
    connection.commit()
    return count


def fetch_run_records(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    record_name: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch records for one run, optionally filtered by record alias."""

    if record_name is None:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM run_records
            WHERE run_id = ?
            ORDER BY record_name, record_id
            """,
            (run_id,),
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM run_records
            WHERE run_id = ? AND record_name = ?
            ORDER BY record_id
            """,
            (run_id, record_name),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def upsert_run_artifact(
    connection: sqlite3.Connection,
    *,
    run_id: str,
    artifact_path: str,
    artifact_type: str,
    size_bytes: int,
    updated_at: str | None = None,
) -> None:
    """Insert or replace a filesystem artifact manifest row."""

    connection.execute(
        """
        INSERT OR REPLACE INTO run_artifacts (
            run_id,
            artifact_path,
            artifact_type,
            size_bytes,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            run_id,
            artifact_path,
            artifact_type,
            size_bytes,
            updated_at or datetime.now(UTC).isoformat(),
        ),
    )
    connection.commit()


def list_run_artifacts(
    connection: sqlite3.Connection,
    *,
    run_id: str,
) -> list[dict[str, Any]]:
    """List filesystem artifacts registered for one run."""

    rows = connection.execute(
        """
        SELECT artifact_path, artifact_type, size_bytes, updated_at
        FROM run_artifacts
        WHERE run_id = ?
        ORDER BY artifact_path
        """,
        (run_id,),
    ).fetchall()
    return [
        {
            "run_id": run_id,
            "artifact_path": row[0],
            "artifact_type": row[1],
            "size_bytes": row[2],
            "updated_at": row[3],
        }
        for row in rows
    ]


def upsert_audit_event(
    connection: sqlite3.Connection,
    event: dict[str, Any] | SerializableRecord,
) -> None:
    """Insert or replace one audit event in durable storage."""

    payload = event.to_dict() if isinstance(event, SerializableRecord) else dict(event)
    event_id = str(payload.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("audit event requires event_id")
    connection.execute(
        """
        INSERT OR REPLACE INTO audit_events (
            event_id,
            event_type,
            actor,
            created_at,
            run_id,
            claim_id,
            document_id,
            source_id,
            payload_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            event_id,
            payload.get("event_type"),
            payload.get("actor"),
            payload.get("created_at"),
            payload.get("run_id"),
            payload.get("claim_id"),
            payload.get("document_id"),
            payload.get("source_id"),
            json.dumps(payload, sort_keys=True),
        ),
    )
    connection.commit()


def fetch_audit_events(
    connection: sqlite3.Connection,
    *,
    run_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fetch durable audit events, optionally scoped to one run."""

    if run_id is None:
        rows = connection.execute(
            "SELECT payload_json FROM audit_events ORDER BY created_at, event_id",
        ).fetchall()
    else:
        rows = connection.execute(
            """
            SELECT payload_json
            FROM audit_events
            WHERE run_id = ?
            ORDER BY created_at, event_id
            """,
            (run_id,),
        ).fetchall()
    return [json.loads(row[0]) for row in rows]


def mirror_run_to_sqlite(
    *,
    db_path: str | Path,
    run_dir: str | Path,
) -> dict[str, Any]:
    """Mirror one JSONL run directory into durable SQLite tables."""

    source = Path(run_dir)
    summary_path = source / "run_summary.json"
    if not summary_path.exists():
        raise ValueError(f"run summary not found: {summary_path}")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    run_id = str(summary.get("run_id") or source.name)
    connection = initialize_sqlite(db_path)
    try:
        upsert_run_summary(connection, summary)
        record_count = 0
        records_dir = source / "records"
        if records_dir.exists():
            for path in sorted(records_dir.glob("*.jsonl")):
                records = read_jsonl(path)
                record_count += upsert_run_records(
                    connection,
                    run_id=run_id,
                    record_name=path.stem,
                    records=records,
                )
        artifact_count = 0
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            upsert_run_artifact(
                connection,
                run_id=run_id,
                artifact_path=relative,
                artifact_type=_artifact_type(path),
                size_bytes=path.stat().st_size,
            )
            artifact_count += 1
    finally:
        connection.close()
    return {
        "run_id": run_id,
        "db_path": str(db_path),
        "record_count": record_count,
        "artifact_count": artifact_count,
    }


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


def _record_type_for_name(record_name: str) -> str:
    """Return a readable record type label for a public record alias."""

    return "".join(part.capitalize() for part in record_name.split("_"))


def _artifact_type(path: Path) -> str:
    """Classify an artifact by path for the manifest table."""

    suffix = path.suffix.lower().lstrip(".")
    if path.name == "run_summary.json":
        return "run_summary"
    if path.parent.name == "records" and suffix == "jsonl":
        return "record_jsonl"
    if path.parent.name == "logs" and suffix == "jsonl":
        return "log_jsonl"
    if suffix in {"html", "json", "md", "txt", "pdf"}:
        return suffix
    return "artifact"


def record_id(payload: dict[str, Any]) -> str:
    """Return the canonical ID field for a serialized record payload."""
    for key in (
        "event_id",
        "review_id",
        "incremental_id",
        "cluster_id",
        "source_id",
        "run_id",
        "item_id",
        "document_id",
        "entity_id",
        "claim_id",
        "candidate_id",
    ):
        value = payload.get(key)
        if value:
            return str(value)
    raise ValueError(f"record has no stable ID field: {sorted(payload)}")
