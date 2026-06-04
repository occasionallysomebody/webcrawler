"""Polite fetching for approved and access-checked crawl items.

Fetching is the point where the pipeline touches external public sources. This
module records headers, status, checksums, cache paths, and errors so every later
claim can be traced back to exactly what was retrieved and when.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
import hashlib
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener

from crawler.models import AccessDecision, DiscoveredItem, FetchedDocument
from crawler.robots import FetchPolicy, make_headers


def fetch_item(
    item: DiscoveredItem,
    decision: AccessDecision,
    *,
    cache_dir: str | Path,
    policy: FetchPolicy = FetchPolicy(),
    opener: Any | None = None,
    retrieved_at: str | None = None,
    previous_document: FetchedDocument | None = None,
    cache_raw: bool = True,
) -> FetchedDocument:
    """Fetch one permitted item and return a structured fetch record."""
    _validate_item_decision(item, decision)
    timestamp = retrieved_at or datetime.now(UTC).isoformat()

    if not decision.allowed:
        return _document(
            item,
            retrieved_at=timestamp,
            fetch_error=f"skipped_access:{decision.reason}",
            metadata={
                "item_id": item.item_id,
                "access_allowed": False,
                "access_reason": decision.reason,
            },
        )

    request = _request(item.url, policy, previous_document)
    request_opener = opener or build_opener()

    try:
        response = request_opener.open(request, timeout=policy.timeout_seconds)
        try:
            body = response.read()
            return _document_from_response(
                item,
                response,
                body,
                cache_dir=cache_dir,
                retrieved_at=timestamp,
                previous_document=previous_document,
                cache_raw=cache_raw,
            )
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except HTTPError as error:
        if error.code == 304 and previous_document is not None:
            return _not_modified_document(
                item,
                previous_document,
                retrieved_at=timestamp,
                metadata=_response_metadata(error.headers)
                | {"item_id": item.item_id, "not_modified": True},
            )
        return _document(
            item,
            status_code=error.code,
            content_type=_header_value(error.headers, "Content-Type"),
            final_url=getattr(error, "url", item.url),
            retrieved_at=timestamp,
            fetch_error=f"http_error:{error.code}",
            metadata=_response_metadata(error.headers) | {"item_id": item.item_id},
        )
    except URLError as error:
        return _document(
            item,
            retrieved_at=timestamp,
            fetch_error=f"url_error:{error.reason}",
            metadata={"item_id": item.item_id},
        )
    except OSError as error:
        return _document(
            item,
            retrieved_at=timestamp,
            fetch_error=f"io_error:{error}",
            metadata={"item_id": item.item_id},
        )


def fetch_items(
    item_decisions: Iterable[tuple[DiscoveredItem, AccessDecision]],
    *,
    cache_dir: str | Path,
    policy: FetchPolicy = FetchPolicy(),
    opener: Any | None = None,
    previous_documents: dict[str, FetchedDocument] | None = None,
    cache_raw: bool = True,
    sleeper: Callable[[float], None] = time.sleep,
) -> list[FetchedDocument]:
    """Fetch many items, preserving item-level failures as records."""
    documents: list[FetchedDocument] = []
    last_allowed_source_id: str | None = None

    for item, decision in item_decisions:
        if decision.allowed and last_allowed_source_id == decision.source_id:
            delay = decision.rate_limit_seconds or 0
            if delay > 0:
                sleeper(delay)

        previous_document = None
        if previous_documents is not None:
            previous_document = previous_documents.get(item.item_id)
            if previous_document is None:
                previous_document = previous_documents.get(item.url)

        document = fetch_item(
            item,
            decision,
            cache_dir=cache_dir,
            policy=policy,
            opener=opener,
            retrieved_at=None,
            previous_document=previous_document,
            cache_raw=cache_raw,
        )
        documents.append(document)

        if decision.allowed:
            last_allowed_source_id = decision.source_id

    return documents


def fetch_log_entry(document: FetchedDocument) -> dict[str, object]:
    """Create a structured log entry for fetch success, skip, or failure."""
    return {
        "stage": "fetch_content",
        "document_id": document.document_id,
        "source_id": document.source_id,
        "url": document.url,
        "status_code": document.status_code,
        "final_url": document.final_url,
        "raw_cache_path": document.raw_cache_path,
        "fetch_error": document.fetch_error,
        "retrieved_at": document.retrieved_at,
    }


def document_id(source_id: str, url: str) -> str:
    """Return a stable document ID for a source URL."""
    digest = hashlib.sha256(f"{source_id}\n{url}".encode("utf-8")).hexdigest()
    return f"doc-{digest[:16]}"


def checksum_bytes(content: bytes) -> str:
    """Return a stable checksum for fetched bytes."""
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def _document_from_response(
    item: DiscoveredItem,
    response: Any,
    body: bytes,
    *,
    cache_dir: str | Path,
    retrieved_at: str,
    previous_document: FetchedDocument | None,
    cache_raw: bool,
) -> FetchedDocument:
    """Support the module's public workflow by computing document from response.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        item (DiscoveredItem): Single discovered URL or document candidate being
            processed.
        response (Any): Value named ``response`` supplied by the caller for this
            pipeline step.
        body (bytes): Value named ``body`` supplied by the caller for this pipeline
            step.
        cache_dir (str | Path): Value named ``cache_dir`` supplied by the caller for
            this pipeline step.
        retrieved_at (str): Value named ``retrieved_at`` supplied by the caller for this
            pipeline step.
        previous_document (FetchedDocument | None): Value named ``previous_document``
            supplied by the caller for this pipeline step.
        cache_raw (bool): Value named ``cache_raw`` supplied by the caller for this
            pipeline step.
    
    Returns:
        FetchedDocument: Result produced for the next pipeline step or caller.
    """
    checksum = checksum_bytes(body)
    headers = getattr(response, "headers", {})
    content_type = _header_value(headers, "Content-Type")
    final_url = response.geturl()
    status_code = response.getcode()
    metadata = _response_metadata(headers) | {"item_id": item.item_id}

    if (
        previous_document is not None
        and previous_document.checksum == checksum
        and previous_document.raw_cache_path
    ):
        return _document(
            item,
            final_url=final_url,
            status_code=status_code,
            content_type=content_type,
            retrieved_at=retrieved_at,
            checksum=checksum,
            raw_cache_path=previous_document.raw_cache_path,
            metadata=metadata
            | {
                "not_modified": True,
                "not_modified_reason": "checksum_match",
                "previous_document_id": previous_document.document_id,
            },
        )

    raw_cache_path = None
    if cache_raw:
        raw_cache_path = str(
            _write_raw_cache(
                cache_dir,
                document_id(item.source_id, item.url),
                body,
                content_type,
                item.url,
            ),
        )

    return _document(
        item,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        retrieved_at=retrieved_at,
        checksum=checksum,
        raw_cache_path=raw_cache_path,
        metadata=metadata,
    )


def _not_modified_document(
    item: DiscoveredItem,
    previous_document: FetchedDocument,
    *,
    retrieved_at: str,
    metadata: dict[str, object],
) -> FetchedDocument:
    """Support the module's public workflow by computing not modified document.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        item (DiscoveredItem): Single discovered URL or document candidate being
            processed.
        previous_document (FetchedDocument): Value named ``previous_document`` supplied
            by the caller for this pipeline step.
        retrieved_at (str): Value named ``retrieved_at`` supplied by the caller for this
            pipeline step.
        metadata (dict[str, object]): Value named ``metadata`` supplied by the caller
            for this pipeline step.
    
    Returns:
        FetchedDocument: Result produced for the next pipeline step or caller.
    """
    return _document(
        item,
        final_url=previous_document.final_url,
        status_code=304,
        content_type=previous_document.content_type,
        retrieved_at=retrieved_at,
        checksum=previous_document.checksum,
        raw_cache_path=previous_document.raw_cache_path,
        metadata=metadata
        | {"previous_document_id": previous_document.document_id},
    )


def _document(
    item: DiscoveredItem,
    *,
    final_url: str | None = None,
    status_code: int | None = None,
    content_type: str | None = None,
    retrieved_at: str | None = None,
    checksum: str | None = None,
    raw_cache_path: str | None = None,
    fetch_error: str | None = None,
    metadata: dict[str, object] | None = None,
) -> FetchedDocument:
    """Support the module's public workflow by computing document.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        item (DiscoveredItem): Single discovered URL or document candidate being
            processed.
        final_url (str | None): Value named ``final_url`` supplied by the caller for
            this pipeline step.
        status_code (int | None): Value named ``status_code`` supplied by the caller for
            this pipeline step.
        content_type (str | None): HTTP content type used to choose an extraction or
            cache strategy.
        retrieved_at (str | None): Value named ``retrieved_at`` supplied by the caller
            for this pipeline step.
        checksum (str | None): Value named ``checksum`` supplied by the caller for this
            pipeline step.
        raw_cache_path (str | None): Value named ``raw_cache_path`` supplied by the
            caller for this pipeline step.
        fetch_error (str | None): Value named ``fetch_error`` supplied by the caller for
            this pipeline step.
        metadata (dict[str, object] | None): Value named ``metadata`` supplied by the
            caller for this pipeline step.
    
    Returns:
        FetchedDocument: Result produced for the next pipeline step or caller.
    """
    return FetchedDocument(
        document_id=document_id(item.source_id, item.url),
        source_id=item.source_id,
        url=item.url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        retrieved_at=retrieved_at,
        checksum=checksum,
        raw_cache_path=raw_cache_path,
        fetch_error=fetch_error,
        metadata=dict(metadata or {}),
    )


def _request(
    url: str,
    policy: FetchPolicy,
    previous_document: FetchedDocument | None,
) -> Request:
    """Support the module's public workflow by computing request.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        url (str): Public URL being normalized, checked, fetched, or cited.
        policy (FetchPolicy): Fetch policy containing user-agent, timeout, retry, and
            rate-limit settings.
        previous_document (FetchedDocument | None): Value named ``previous_document``
            supplied by the caller for this pipeline step.
    
    Returns:
        Request: Result produced for the next pipeline step or caller.
    """
    headers = make_headers(policy)
    if previous_document is not None:
        etag = previous_document.metadata.get("etag")
        last_modified = previous_document.metadata.get("last_modified")
        if isinstance(etag, str) and etag:
            headers["If-None-Match"] = etag
        if isinstance(last_modified, str) and last_modified:
            headers["If-Modified-Since"] = last_modified
    return Request(url, headers=headers, method="GET")


def _write_raw_cache(
    cache_dir: str | Path,
    doc_id: str,
    body: bytes,
    content_type: str | None,
    url: str,
) -> Path:
    """Support the module's public workflow by computing write raw cache.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        cache_dir (str | Path): Value named ``cache_dir`` supplied by the caller for
            this pipeline step.
        doc_id (str): Value named ``doc_id`` supplied by the caller for this pipeline
            step.
        body (bytes): Value named ``body`` supplied by the caller for this pipeline
            step.
        content_type (str | None): HTTP content type used to choose an extraction or
            cache strategy.
        url (str): Public URL being normalized, checked, fetched, or cited.
    
    Returns:
        Path: Resolved path to the file or directory created by the helper.
    """
    target_dir = Path(cache_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target_path = target_dir / f"{doc_id}{_extension(content_type, url)}"
    target_path.write_bytes(body)
    return target_path


def _extension(content_type: str | None, url: str) -> str:
    """Support the module's public workflow by computing extension.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        content_type (str | None): HTTP content type used to choose an extraction or
            cache strategy.
        url (str): Public URL being normalized, checked, fetched, or cited.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    lowered_type = (content_type or "").split(";", 1)[0].strip().lower()
    if lowered_type == "text/html":
        return ".html"
    if lowered_type == "application/pdf":
        return ".pdf"
    if lowered_type == "application/json":
        return ".json"
    suffix = Path(url.split("?", 1)[0]).suffix
    if suffix:
        return suffix
    return ".bin"


def _response_metadata(headers: Any) -> dict[str, object]:
    """Support the module's public workflow by computing response metadata.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        headers (Any): HTTP header mapping returned by a server or sent with a request.
    
    Returns:
        dict[str, object]: Structured log entry suitable for JSONL audit logs.
    """
    metadata: dict[str, object] = {}
    for metadata_key, header_name in (
        ("etag", "ETag"),
        ("last_modified", "Last-Modified"),
        ("content_length", "Content-Length"),
    ):
        value = _header_value(headers, header_name)
        if value:
            metadata[metadata_key] = value
    return metadata


def _header_value(headers: Any, name: str) -> str | None:
    """Support the module's public workflow by computing header value.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        headers (Any): HTTP header mapping returned by a server or sent with a request.
        name (str): Value named ``name`` supplied by the caller for this pipeline step.
    
    Returns:
        str | None: Result produced for the next pipeline step or caller.
    """
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is None:
            value = getter(name.lower())
        if value is not None:
            return str(value)
    return None


def _validate_item_decision(
    item: DiscoveredItem,
    decision: AccessDecision,
) -> None:
    """Support the module's public workflow by computing validate item decision.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        item (DiscoveredItem): Single discovered URL or document candidate being
            processed.
        decision (AccessDecision): Access decision that records whether a URL may be
            fetched.
    
    Returns:
        None: This function is used for its side effect and does not return a value.
    
    Raises:
        ValueError: Raised when validation or downstream access fails and the caller
            should stop or return an explicit error.
    """
    if item.item_id != decision.item_id:
        raise ValueError("access decision item_id does not match discovered item")
    if item.source_id != decision.source_id:
        raise ValueError("access decision source_id does not match discovered item")
    if item.url != decision.url:
        raise ValueError("access decision url does not match discovered item")
