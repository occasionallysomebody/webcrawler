"""Incremental crawl helpers for scheduled monitoring runs.

This module compares the current fetch records with a previous run. It keeps the
logic separate from fetching so network code remains focused on HTTP behavior
while orchestration can decide which unchanged documents should skip downstream
extraction and claim generation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from crawler.models import FetchedDocument, IncrementalFetch
from crawler.storage import read_jsonl


INCREMENTAL_STATUSES = {"new", "changed", "unchanged", "failed", "skipped"}


def load_previous_documents(
    output_root: str | Path,
    *,
    current_run_id: str,
    previous_run_id: str | None = None,
) -> tuple[str | None, dict[str, FetchedDocument]]:
    """Load fetched documents from the chosen previous run.

    Args:
        output_root (str | Path): Root directory that contains run folders.
        current_run_id (str): Run currently being executed. It is excluded when
            auto-selecting the latest prior run.
        previous_run_id (str | None): Optional explicit previous run ID.

    Returns:
        tuple[str | None, dict[str, FetchedDocument]]: Previous run ID and
        documents keyed by URL and item ID where available.
    """

    root = Path(output_root)
    selected_run_id = previous_run_id or latest_completed_run_id(
        root,
        exclude_run_id=current_run_id,
    )
    if selected_run_id is None:
        return None, {}

    records_path = root / selected_run_id / "records" / "fetched_documents.jsonl"
    documents = _documents_from_jsonl(records_path)
    keyed: dict[str, FetchedDocument] = {}
    for document in documents:
        keyed[document.url] = document
        item_id = document.metadata.get("item_id")
        if isinstance(item_id, str) and item_id:
            keyed[item_id] = document
    return selected_run_id, keyed


def latest_completed_run_id(
    output_root: str | Path,
    *,
    exclude_run_id: str,
) -> str | None:
    """Return the newest prior run with fetched document records.

    Args:
        output_root (str | Path): Root directory that contains run folders.
        exclude_run_id (str): Current run ID to ignore.

    Returns:
        str | None: Latest usable run ID, or ``None`` if no prior metadata is
        available.
    """

    root = Path(output_root)
    if not root.exists():
        return None

    candidates: list[tuple[str, str]] = []
    for run_dir in root.iterdir():
        if not run_dir.is_dir() or run_dir.name == exclude_run_id:
            continue
        summary_path = run_dir / "run_summary.json"
        records_path = run_dir / "records" / "fetched_documents.jsonl"
        if not summary_path.exists() or not records_path.exists():
            continue
        try:
            summary = _read_summary(summary_path)
        except ValueError:
            continue
        if summary.get("status") not in {"success", "partial_success"}:
            continue
        sort_key = str(summary.get("finished_at") or summary.get("started_at") or run_dir.name)
        candidates.append((sort_key, run_dir.name))

    if not candidates:
        return None
    return sorted(candidates)[-1][1]


def classify_incremental_fetches(
    *,
    run_id: str,
    documents: list[FetchedDocument],
    previous_documents: dict[str, FetchedDocument],
    previous_run_id: str | None,
) -> list[IncrementalFetch]:
    """Classify current fetch records against previous run metadata.

    Args:
        run_id (str): Current run identifier.
        documents (list[FetchedDocument]): Current fetch records.
        previous_documents (dict[str, FetchedDocument]): Previous documents
            keyed by URL or item ID.
        previous_run_id (str | None): Previous run used for comparison.

    Returns:
        list[IncrementalFetch]: Comparison records written to
        ``records/incremental_fetches.jsonl``.
    """

    records = []
    for document in documents:
        previous = previous_documents.get(document.url)
        item_id = document.metadata.get("item_id")
        if previous is None and isinstance(item_id, str):
            previous = previous_documents.get(item_id)
        status, reason = _incremental_status(document, previous)
        records.append(
            IncrementalFetch(
                incremental_id=f"inc-{run_id}-{document.document_id}",
                run_id=run_id,
                source_id=document.source_id,
                url=document.url,
                document_id=document.document_id,
                status=status,
                current_checksum=document.checksum,
                previous_run_id=previous_run_id,
                previous_document_id=previous.document_id if previous else None,
                previous_checksum=previous.checksum if previous else None,
                reason=reason,
                metadata={
                    "status_code": document.status_code,
                    "fetch_error": document.fetch_error,
                    "not_modified": document.metadata.get("not_modified", False),
                    "etag": document.metadata.get("etag"),
                    "last_modified": document.metadata.get("last_modified"),
                },
            )
        )
    return records


def changed_document_ids(records: list[IncrementalFetch]) -> set[str]:
    """Return document IDs that should continue through extraction.

    Args:
        records (list[IncrementalFetch]): Incremental comparison records.

    Returns:
        set[str]: Document IDs with ``new`` or ``changed`` status.
    """

    return {
        record.document_id
        for record in records
        if record.status in {"new", "changed"}
    }


def incremental_summary(records: list[IncrementalFetch]) -> dict[str, int]:
    """Count incremental records by status.

    Args:
        records (list[IncrementalFetch]): Incremental comparison records.

    Returns:
        dict[str, int]: Counts for all known statuses.
    """

    counts = {status: 0 for status in sorted(INCREMENTAL_STATUSES)}
    for record in records:
        counts[record.status] = counts.get(record.status, 0) + 1
    return counts


def incremental_log_entry(records: list[IncrementalFetch]) -> dict[str, object]:
    """Create a structured run log entry for incremental comparison.

    Args:
        records (list[IncrementalFetch]): Incremental comparison records.

    Returns:
        dict[str, object]: JSON-safe run log event.
    """

    return {
        "stage": "classify_incremental_fetches",
        **incremental_summary(records),
    }


def _incremental_status(
    document: FetchedDocument,
    previous: FetchedDocument | None,
) -> tuple[str, str]:
    """Classify one fetched document.

    Args:
        document (FetchedDocument): Current fetch record.
        previous (FetchedDocument | None): Previous matching document.

    Returns:
        tuple[str, str]: Status and reason.
    """

    if document.fetch_error:
        if document.fetch_error.startswith("skipped_access:"):
            return "skipped", document.fetch_error
        return "failed", document.fetch_error
    if previous is None:
        return "new", "no_previous_document"
    if document.status_code == 304 or document.metadata.get("not_modified") is True:
        return "unchanged", str(document.metadata.get("not_modified_reason") or "not_modified")
    if document.checksum and previous.checksum and document.checksum != previous.checksum:
        return "changed", "checksum_changed"
    if document.checksum and previous.checksum and document.checksum == previous.checksum:
        return "unchanged", "checksum_match"
    return "changed", "missing_comparable_checksum"


def _documents_from_jsonl(path: Path) -> list[FetchedDocument]:
    """Load fetched documents from JSONL.

    Args:
        path (Path): JSONL path.

    Returns:
        list[FetchedDocument]: Parsed fetched document records.
    """

    return [FetchedDocument(**row) for row in read_jsonl(path)]


def _read_summary(path: Path) -> dict[str, Any]:
    """Read a run summary JSON file.

    Args:
        path (Path): Summary path.

    Returns:
        dict[str, Any]: Parsed summary payload.
    """

    import json

    return json.loads(path.read_text(encoding="utf-8"))
