"""Source health and crawl-frontier assessment.

A production crawler needs to know which sources are useful, stale, blocked, or
noisy. This module summarizes access, fetch, extraction, and claim-yield signals
so operators can prioritize retries and source review.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
from typing import Iterable

from crawler.models import (
    AccessDecision,
    Claim,
    DiscoveredItem,
    ExtractedDocument,
    FetchedDocument,
    RetryCandidate,
    Source,
    SourceHealth,
)


def assess_source_health(
    *,
    run_id: str,
    sources: list[Source],
    discovered_items: list[DiscoveredItem],
    access_decisions: list[AccessDecision],
    fetched_documents: list[FetchedDocument],
    extracted_documents: list[ExtractedDocument],
    claims: list[Claim],
) -> tuple[list[SourceHealth], list[RetryCandidate]]:
    """Build per-source health records and retry/frontier candidates."""
    item_counts = _count_by_source(discovered_items)
    decisions_by_source = _group_by_source(access_decisions)
    documents_by_source = _group_by_source(fetched_documents)
    extraction_by_doc = {document.document_id: document for document in extracted_documents}
    claims_by_doc = _claims_by_document(claims)
    health_records: list[SourceHealth] = []
    retry_candidates: list[RetryCandidate] = []

    for source in sources:
        source_decisions = decisions_by_source[source.source_id]
        source_documents = documents_by_source[source.source_id]
        fetch_successes = [document for document in source_documents if _fetch_success(document)]
        fetch_failures = [document for document in source_documents if document.fetch_error]
        source_extractions = [
            extraction_by_doc[document.document_id]
            for document in source_documents
            if document.document_id in extraction_by_doc
        ]
        extraction_successes = [
            extraction for extraction in source_extractions if not extraction.error
        ]
        extraction_failures = [
            extraction for extraction in source_extractions if extraction.error
        ]
        source_claims = [
            claim
            for document in source_documents
            for claim in claims_by_doc.get(document.document_id, [])
        ]
        access_allowed = sum(1 for decision in source_decisions if decision.allowed)
        access_denied = sum(1 for decision in source_decisions if not decision.allowed)
        health_score = _health_score(
            items_discovered=item_counts[source.source_id],
            access_allowed=access_allowed,
            access_denied=access_denied,
            fetch_successes=len(fetch_successes),
            fetch_failures=len(fetch_failures),
            extraction_successes=len(extraction_successes),
            extraction_failures=len(extraction_failures),
            claims_extracted=len(source_claims),
        )
        health_records.append(
            SourceHealth(
                source_id=source.source_id,
                run_id=run_id,
                status=_status(health_score, access_allowed, access_denied, source_claims),
                health_score=health_score,
                items_discovered=item_counts[source.source_id],
                access_allowed=access_allowed,
                access_denied=access_denied,
                documents_fetched=len(source_documents),
                fetch_successes=len(fetch_successes),
                fetch_failures=len(fetch_failures),
                extraction_successes=len(extraction_successes),
                extraction_failures=len(extraction_failures),
                claims_extracted=len(source_claims),
                claim_yield=_ratio(len(source_claims), max(1, len(fetch_successes))),
                notes=_notes(
                    access_allowed=access_allowed,
                    access_denied=access_denied,
                    fetch_failures=len(fetch_failures),
                    extraction_failures=len(extraction_failures),
                    claims_extracted=len(source_claims),
                ),
                metadata={
                    "source_name": source.name,
                    "tier": source.tier,
                    "publisher_type": source.publisher_type,
                },
            )
        )
        retry_candidates.extend(_retry_candidates_for_decisions(source_decisions))
        retry_candidates.extend(_retry_candidates_for_documents(fetch_failures))
        retry_candidates.extend(_retry_candidates_for_extractions(extraction_failures, source_documents))

    return health_records, retry_candidates


def source_health_log_entry(health: SourceHealth) -> dict[str, object]:
    """Create a structured log entry for source health assessment."""
    return {
        "stage": "assess_source_health",
        "source_id": health.source_id,
        "status": health.status,
        "health_score": health.health_score,
        "claims_extracted": health.claims_extracted,
        "fetch_failures": health.fetch_failures,
        "access_denied": health.access_denied,
    }


def frontier_log_entry(candidates: Iterable[RetryCandidate]) -> dict[str, object]:
    """Create a structured log entry for retry/frontier output."""
    candidate_list = list(candidates)
    return {
        "stage": "build_crawl_frontier",
        "retry_candidates": len(candidate_list),
        "retryable_candidates": sum(1 for item in candidate_list if item.retryable),
        "permanent_skips": sum(1 for item in candidate_list if not item.retryable),
    }


def _count_by_source(items: list[DiscoveredItem]) -> defaultdict[str, int]:
    """Support the module's public workflow by computing count by source.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        items (list[DiscoveredItem]): Discovered crawl items being limited, checked,
            fetched, or converted.
    
    Returns:
        defaultdict[str, int]: Result produced for the next pipeline step or caller.
    """
    counts: defaultdict[str, int] = defaultdict(int)
    for item in items:
        counts[item.source_id] += 1
    return counts


def _group_by_source(records):
    """Support the module's public workflow by computing group by source.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        records (Any): Iterable of pipeline records to process.
    
    Returns:
        Any: Result produced for the next pipeline step or caller.
    """
    grouped = defaultdict(list)
    for record in records:
        grouped[record.source_id].append(record)
    return grouped


def _claims_by_document(claims: list[Claim]) -> defaultdict[str, list[Claim]]:
    """Support the module's public workflow by computing claims by document.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        claims (list[Claim]): Claim records extracted from cleaned and redacted
            documents.
    
    Returns:
        defaultdict[str, list[Claim]]: Result produced for the next pipeline step or
            caller.
    """
    grouped: defaultdict[str, list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[claim.document_id].append(claim)
    return grouped


def _fetch_success(document: FetchedDocument) -> bool:
    """Support the module's public workflow by computing fetch success.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        document (FetchedDocument): Document record being transformed by this helper.
    
    Returns:
        bool: Boolean decision used by the caller to choose the next pipeline step.
    """
    return document.fetch_error is None and (
        document.status_code is None
        or 200 <= document.status_code < 300
        or document.status_code == 304
    )


def _health_score(
    *,
    items_discovered: int,
    access_allowed: int,
    access_denied: int,
    fetch_successes: int,
    fetch_failures: int,
    extraction_successes: int,
    extraction_failures: int,
    claims_extracted: int,
) -> float:
    """Support the module's public workflow by computing health score.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        items_discovered (int): Value named ``items_discovered`` supplied by the caller
            for this pipeline step.
        access_allowed (int): Value named ``access_allowed`` supplied by the caller for
            this pipeline step.
        access_denied (int): Value named ``access_denied`` supplied by the caller for
            this pipeline step.
        fetch_successes (int): Value named ``fetch_successes`` supplied by the caller
            for this pipeline step.
        fetch_failures (int): Value named ``fetch_failures`` supplied by the caller for
            this pipeline step.
        extraction_successes (int): Value named ``extraction_successes`` supplied by the
            caller for this pipeline step.
        extraction_failures (int): Value named ``extraction_failures`` supplied by the
            caller for this pipeline step.
        claims_extracted (int): Value named ``claims_extracted`` supplied by the caller
            for this pipeline step.
    
    Returns:
        float: Normalized score between 0 and 1 unless the function description says
            otherwise.
    """
    if items_discovered == 0:
        return 0.0
    access_score = _ratio(access_allowed, access_allowed + access_denied)
    fetch_score = _ratio(fetch_successes, fetch_successes + fetch_failures)
    extraction_score = _ratio(
        extraction_successes,
        extraction_successes + extraction_failures,
    )
    yield_score = min(1.0, claims_extracted / max(1, fetch_successes * 3))
    return round(
        0.25 * access_score
        + 0.30 * fetch_score
        + 0.25 * extraction_score
        + 0.20 * yield_score,
        3,
    )


def _status(
    health_score: float,
    access_allowed: int,
    access_denied: int,
    claims: list[Claim],
) -> str:
    """Support the module's public workflow by computing status.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        health_score (float): Value named ``health_score`` supplied by the caller for
            this pipeline step.
        access_allowed (int): Value named ``access_allowed`` supplied by the caller for
            this pipeline step.
        access_denied (int): Value named ``access_denied`` supplied by the caller for
            this pipeline step.
        claims (list[Claim]): Claim records extracted from cleaned and redacted
            documents.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    if access_allowed == 0 and access_denied > 0:
        return "blocked"
    if health_score >= 0.8 and claims:
        return "high_value"
    if health_score >= 0.65:
        return "healthy"
    if health_score > 0:
        return "degraded"
    return "no_activity"


def _notes(
    *,
    access_allowed: int,
    access_denied: int,
    fetch_failures: int,
    extraction_failures: int,
    claims_extracted: int,
) -> list[str]:
    """Support the module's public workflow by computing notes.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        access_allowed (int): Value named ``access_allowed`` supplied by the caller for
            this pipeline step.
        access_denied (int): Value named ``access_denied`` supplied by the caller for
            this pipeline step.
        fetch_failures (int): Value named ``fetch_failures`` supplied by the caller for
            this pipeline step.
        extraction_failures (int): Value named ``extraction_failures`` supplied by the
            caller for this pipeline step.
        claims_extracted (int): Value named ``claims_extracted`` supplied by the caller
            for this pipeline step.
    
    Returns:
        list[str]: Result produced for the next pipeline step or caller.
    """
    notes = []
    if access_denied:
        notes.append("access_denials_present")
    if access_allowed == 0 and access_denied:
        notes.append("all_access_denied")
    if fetch_failures:
        notes.append("fetch_failures_present")
    if extraction_failures:
        notes.append("extraction_failures_present")
    if claims_extracted == 0:
        notes.append("no_claim_yield")
    return notes


def _retry_candidates_for_decisions(
    decisions: list[AccessDecision],
) -> list[RetryCandidate]:
    """Support the module's public workflow by computing retry candidates for decisions.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        decisions (list[AccessDecision]): Access decision records created before
            fetching content.
    
    Returns:
        list[RetryCandidate]: Result produced for the next pipeline step or caller.
    """
    candidates: list[RetryCandidate] = []
    for decision in decisions:
        if decision.allowed:
            continue
        retryable = decision.reason == "robots_required_but_not_loaded"
        candidates.append(
            _candidate(
                source_id=decision.source_id,
                url=decision.url,
                reason=f"access_denied:{decision.reason}",
                retryable=retryable,
                priority="low" if retryable else "skip",
                item_id=decision.item_id,
                next_action="retry_robots_lookup" if retryable else "review_access_policy",
            )
        )
    return candidates


def _retry_candidates_for_documents(
    documents: list[FetchedDocument],
) -> list[RetryCandidate]:
    """Support the module's public workflow by computing retry candidates for documents.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        documents (list[FetchedDocument]): Fetched or extracted documents available to
            the current pipeline step.
    
    Returns:
        list[RetryCandidate]: Result produced for the next pipeline step or caller.
    """
    candidates: list[RetryCandidate] = []
    for document in documents:
        retryable = _retryable_fetch_error(document.fetch_error)
        candidates.append(
            _candidate(
                source_id=document.source_id,
                url=document.url,
                reason=f"fetch_error:{document.fetch_error}",
                retryable=retryable,
                priority="high" if retryable else "skip",
                document_id=document.document_id,
                next_action="retry_fetch" if retryable else "manual_review",
            )
        )
    return candidates


def _retry_candidates_for_extractions(
    extractions: list[ExtractedDocument],
    documents: list[FetchedDocument],
) -> list[RetryCandidate]:
    """Support the module's public workflow by computing retry candidates for
    extractions.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        extractions (list[ExtractedDocument]): Value named ``extractions`` supplied by
            the caller for this pipeline step.
        documents (list[FetchedDocument]): Fetched or extracted documents available to
            the current pipeline step.
    
    Returns:
        list[RetryCandidate]: Result produced for the next pipeline step or caller.
    """
    document_by_id = {document.document_id: document for document in documents}
    candidates = []
    for extraction in extractions:
        document = document_by_id.get(extraction.document_id)
        candidates.append(
            _candidate(
                source_id=extraction.source_id,
                url=extraction.url,
                reason=f"extraction_error:{extraction.error}",
                retryable=False,
                priority="skip",
                document_id=extraction.document_id,
                next_action="configure_extractor",
                item_id=str(document.metadata.get("item_id")) if document else None,
            )
        )
    return candidates


def _retryable_fetch_error(error: str | None) -> bool:
    """Support the module's public workflow by computing retryable fetch error.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        error (str | None): Value named ``error`` supplied by the caller for this
            pipeline step.
    
    Returns:
        bool: Boolean decision used by the caller to choose the next pipeline step.
    """
    if error is None:
        return False
    return error.startswith(("url_error:", "io_error:", "http_error:5"))


def _candidate(
    *,
    source_id: str,
    url: str,
    reason: str,
    retryable: bool,
    priority: str,
    item_id: str | None = None,
    document_id: str | None = None,
    next_action: str,
) -> RetryCandidate:
    """Support the module's public workflow by computing candidate.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        url (str): Public URL being normalized, checked, fetched, or cited.
        reason (str): Value named ``reason`` supplied by the caller for this pipeline
            step.
        retryable (bool): Value named ``retryable`` supplied by the caller for this
            pipeline step.
        priority (str): Value named ``priority`` supplied by the caller for this
            pipeline step.
        item_id (str | None): Value named ``item_id`` supplied by the caller for this
            pipeline step.
        document_id (str | None): Value named ``document_id`` supplied by the caller for
            this pipeline step.
        next_action (str): Value named ``next_action`` supplied by the caller for this
            pipeline step.
    
    Returns:
        RetryCandidate: Result produced for the next pipeline step or caller.
    """
    candidate_id = _stable_id(source_id, url, reason, document_id or item_id or "")
    return RetryCandidate(
        candidate_id=candidate_id,
        source_id=source_id,
        url=url,
        reason=reason,
        retryable=retryable,
        priority=priority,
        item_id=item_id,
        document_id=document_id,
        next_action=next_action,
    )


def _stable_id(*parts: str) -> str:
    """Support the module's public workflow by computing stable id.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        parts (str): Value named ``parts`` supplied by the caller for this pipeline
            step.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"frontier-{digest[:16]}"


def _ratio(numerator: int, denominator: int) -> float:
    """Support the module's public workflow by computing ratio.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        numerator (int): Top value in a ratio calculation.
        denominator (int): Bottom value in a ratio calculation. Zero is handled
            defensively.
    
    Returns:
        float: Normalized score between 0 and 1 unless the function description says
            otherwise.
    """
    if denominator <= 0:
        return 0.0
    return numerator / denominator
