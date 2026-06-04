from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.models import Claim, FetchedDocument, Source
from crawler.storage import (
    append_jsonl,
    fetch_run_records,
    fetch_run_summary,
    fetch_records,
    find_documents_by_url_checksum,
    initialize_sqlite,
    list_run_artifacts,
    list_run_summaries,
    mirror_run_to_sqlite,
    read_jsonl,
    storage_log_entry,
    upsert_run_records,
    upsert_run_summary,
    upsert_records,
)


def test_append_and_read_jsonl_records() -> None:
    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "records" / "sources.jsonl"
        count = append_jsonl(
            path,
            [
                Source(
                    "source-a",
                    "Source A",
                    "tier_1",
                    "multilateral",
                    "https://a.example",
                    "manual_seed",
                ),
            ],
        )

        rows = read_jsonl(path)

    assert count == 1
    assert rows[0]["source_id"] == "source-a"


def test_sqlite_upserts_records_and_queries_by_type() -> None:
    with TemporaryDirectory() as tmp_dir:
        connection = initialize_sqlite(Path(tmp_dir) / "crawler.sqlite")
        count = upsert_records(
            connection,
            [
                Source(
                    "source-a",
                    "Source A",
                    "tier_1",
                    "multilateral",
                    "https://a.example",
                    "manual_seed",
                ),
                Claim(
                    claim_id="claim-a",
                    document_id="doc-a",
                    claim_text="Example claim.",
                    claim_type="summary",
                ),
            ],
            created_at="2026-06-03T00:00:00+00:00",
        )
        claims = fetch_records(connection, "Claim")
        all_records = fetch_records(connection)
        schema_version = connection.execute(
            "SELECT value FROM schema_info WHERE key='schema_version'",
        ).fetchone()[0]
        connection.close()

    assert count == 2
    assert claims == [
        {
            "claim_id": "claim-a",
            "claim_text": "Example claim.",
            "claim_type": "summary",
            "confidence": None,
            "document_id": "doc-a",
            "entities": [],
            "evidence_excerpt": "",
            "extraction_method": "",
            "metadata": {},
        },
    ]
    assert len(all_records) == 2
    assert schema_version == "2"


def test_sqlite_replaces_duplicate_record_ids_and_finds_document_duplicates() -> None:
    with TemporaryDirectory() as tmp_dir:
        connection = initialize_sqlite(Path(tmp_dir) / "crawler.sqlite")
        first = FetchedDocument(
            document_id="doc-a",
            source_id="source-a",
            url="https://example.org/report",
            checksum="sha256:abc",
            status_code=200,
        )
        updated = FetchedDocument(
            document_id="doc-a",
            source_id="source-a",
            url="https://example.org/report",
            checksum="sha256:abc",
            status_code=304,
        )

        upsert_records(connection, [first, updated])
        rows = find_documents_by_url_checksum(
            connection,
            url="https://example.org/report",
            checksum="sha256:abc",
        )
        connection.close()

    assert len(rows) == 1
    assert rows[0]["status_code"] == 304


def test_storage_log_entry() -> None:
    assert storage_log_entry(
        destination="data/documents.jsonl",
        record_count=2,
        storage_type="jsonl",
    ) == {
        "stage": "store_records",
        "storage_type": "jsonl",
        "destination": "data/documents.jsonl",
        "record_count": 2,
    }


def test_sqlite_stores_run_scoped_records_and_summaries() -> None:
    with TemporaryDirectory() as tmp_dir:
        connection = initialize_sqlite(Path(tmp_dir) / "crawler.sqlite")
        summary = {
            "run_id": "run-1",
            "status": "success",
            "started_at": "2026-06-04T00:00:00+00:00",
            "claims_extracted": 1,
        }
        upsert_run_summary(connection, summary)
        upsert_run_records(
            connection,
            run_id="run-1",
            record_name="claims",
            records=[
                Claim(
                    claim_id="claim-a",
                    document_id="doc-a",
                    claim_text="Example claim.",
                    claim_type="summary",
                ),
            ],
        )
        fetched_summary = fetch_run_summary(connection, "run-1")
        listed = list_run_summaries(connection)
        claims = fetch_run_records(
            connection,
            run_id="run-1",
            record_name="claims",
        )
        connection.close()

    assert fetched_summary == summary
    assert listed[0]["run_id"] == "run-1"
    assert claims[0]["claim_id"] == "claim-a"


def test_mirror_run_to_sqlite_registers_records_and_artifacts() -> None:
    with TemporaryDirectory() as tmp_dir:
        run_dir = Path(tmp_dir) / "runs" / "run-1"
        records_dir = run_dir / "records"
        records_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            '{"run_id": "run-1", "status": "success"}',
            encoding="utf-8",
        )
        append_jsonl(
            records_dir / "sources.jsonl",
            [
                Source(
                    "source-a",
                    "Source A",
                    "tier_1",
                    "multilateral",
                    "https://a.example",
                    "manual_seed",
                ),
            ],
        )
        db_path = Path(tmp_dir) / "storage" / "crawler.sqlite"

        result = mirror_run_to_sqlite(db_path=db_path, run_dir=run_dir)
        connection = initialize_sqlite(db_path)
        summary = fetch_run_summary(connection, "run-1")
        sources = fetch_run_records(
            connection,
            run_id="run-1",
            record_name="sources",
        )
        artifacts = list_run_artifacts(connection, run_id="run-1")
        connection.close()

    assert result["record_count"] == 1
    assert summary["status"] == "success"
    assert sources[0]["source_id"] == "source-a"
    assert {artifact["artifact_path"] for artifact in artifacts} >= {
        "run_summary.json",
        "records/sources.jsonl",
    }
