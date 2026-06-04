"""Stable pipeline record definitions.

The crawler passes dataclass records between stages instead of anonymous
dictionaries. That makes artifacts easier to serialize, test, inspect in JSONL,
and explain to analysts who need provenance for every source, document, claim,
and score.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, is_dataclass
import json
from typing import Any


def _normalize(value: Any) -> Any:
    """Convert nested dataclasses into plain JSON-serializable structures."""
    if is_dataclass(value):
        return {key: _normalize(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


@dataclass(slots=True)
class SerializableRecord:
    """Base record with helpers shared across pipeline models."""

    def to_dict(self) -> dict[str, Any]:
        """Compute or perform to dict for the crawler pipeline.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Returns:
            dict[str, Any]: Dictionary response that FastAPI serializes to JSON for the
                frontend or caller.
        """
        return _normalize(self)

    def to_json(self) -> str:
        """Compute or perform to json for the crawler pipeline.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Returns:
            str: String value ready for display, storage, or downstream parsing.
        """
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(slots=True)
class Source(SerializableRecord):
    """Represent the ``Source`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        name (str): Stored value named ``name`` that travels with this record.
        tier (str): Stored value named ``tier`` that travels with this record.
        publisher_type (str): Stored value named ``publisher_type`` that travels with
            this record.
        base_url (str): Source-level URL used as the origin for robots and relative URL
            handling.
        access_method (str): Stored value named ``access_method`` that travels with this
            record.
        rate_limit_seconds (float | None): Stored value named ``rate_limit_seconds``
            that travels with this record.
        robots_required (bool): Stored value named ``robots_required`` that travels with
            this record.
        enabled (bool): Stored value named ``enabled`` that travels with this record.
        notes (str): Stored value named ``notes`` that travels with this record.
        allowed_paths (list[str]): Stored value named ``allowed_paths`` that travels
            with this record.
        blocked_paths (list[str]): Stored value named ``blocked_paths`` that travels
            with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    source_id: str
    name: str
    tier: str
    publisher_type: str
    base_url: str
    access_method: str
    rate_limit_seconds: float | None = None
    robots_required: bool = True
    enabled: bool = True
    notes: str = ""
    allowed_paths: list[str] = field(default_factory=list)
    blocked_paths: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CrawlRun(SerializableRecord):
    """Represent the ``CrawlRun`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        run_id (str): Stable run identifier used to locate records and make logs
            reproducible.
        started_at (str): Stored value named ``started_at`` that travels with this
            record.
        finished_at (str | None): Stored value named ``finished_at`` that travels with
            this record.
        status (str): Stored value named ``status`` that travels with this record.
        enabled_stages (list[str]): Stored value named ``enabled_stages`` that travels
            with this record.
        max_sources (int | None): Stored value named ``max_sources`` that travels with
            this record.
        max_items_per_source (int | None): Stored value named ``max_items_per_source``
            that travels with this record.
        max_fetches (int | None): Stored value named ``max_fetches`` that travels with
            this record.
        output_dir (str | None): Stored value named ``output_dir`` that travels with
            this record.
        errors (list[dict[str, Any]]): Stored value named ``errors`` that travels with
            this record.
    """
    run_id: str
    started_at: str
    finished_at: str | None = None
    status: str = "pending"
    enabled_stages: list[str] = field(default_factory=list)
    max_sources: int | None = None
    max_items_per_source: int | None = None
    max_fetches: int | None = None
    output_dir: str | None = None
    errors: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class DiscoveredItem(SerializableRecord):
    """Represent the ``DiscoveredItem`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        item_id (str): Stored value named ``item_id`` that travels with this record.
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        url (str): Public URL being normalized, checked, fetched, or cited.
        discovery_method (str): Stored value named ``discovery_method`` that travels
            with this record.
        discovered_at (str): Stored value named ``discovered_at`` that travels with this
            record.
        title (str | None): Stored value named ``title`` that travels with this record.
        published_at (str | None): Stored value named ``published_at`` that travels with
            this record.
        content_type_hint (str | None): Stored value named ``content_type_hint`` that
            travels with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    item_id: str
    source_id: str
    url: str
    discovery_method: str
    discovered_at: str
    title: str | None = None
    published_at: str | None = None
    content_type_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AccessDecision(SerializableRecord):
    """Represent the ``AccessDecision`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        item_id (str): Stored value named ``item_id`` that travels with this record.
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        url (str): Public URL being normalized, checked, fetched, or cited.
        allowed (bool): Stored value named ``allowed`` that travels with this record.
        reason (str): Stored value named ``reason`` that travels with this record.
        checked_at (str): Stored value named ``checked_at`` that travels with this
            record.
        robots_required (bool): Stored value named ``robots_required`` that travels with
            this record.
        user_agent (str): Stored value named ``user_agent`` that travels with this
            record.
        rate_limit_seconds (float | None): Stored value named ``rate_limit_seconds``
            that travels with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    item_id: str
    source_id: str
    url: str
    allowed: bool
    reason: str
    checked_at: str
    robots_required: bool = True
    user_agent: str = ""
    rate_limit_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FetchedDocument(SerializableRecord):
    """Represent the ``FetchedDocument`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        url (str): Public URL being normalized, checked, fetched, or cited.
        final_url (str | None): Stored value named ``final_url`` that travels with this
            record.
        status_code (int | None): Stored value named ``status_code`` that travels with
            this record.
        content_type (str | None): HTTP content type used to choose an extraction or
            cache strategy.
        retrieved_at (str | None): Stored value named ``retrieved_at`` that travels with
            this record.
        checksum (str | None): Stored value named ``checksum`` that travels with this
            record.
        raw_cache_path (str | None): Stored value named ``raw_cache_path`` that travels
            with this record.
        fetch_error (str | None): Stored value named ``fetch_error`` that travels with
            this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    document_id: str
    source_id: str
    url: str
    final_url: str | None = None
    status_code: int | None = None
    content_type: str | None = None
    retrieved_at: str | None = None
    checksum: str | None = None
    raw_cache_path: str | None = None
    fetch_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExtractedDocument(SerializableRecord):
    """Represent the ``ExtractedDocument`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        url (str): Public URL being normalized, checked, fetched, or cited.
        title (str | None): Stored value named ``title`` that travels with this record.
        published_at (str | None): Stored value named ``published_at`` that travels with
            this record.
        extracted_text (str): Stored value named ``extracted_text`` that travels with
            this record.
        extraction_method (str): Stored value named ``extraction_method`` that travels
            with this record.
        extraction_quality (str): Stored value named ``extraction_quality`` that travels
            with this record.
        page_count (int | None): Stored value named ``page_count`` that travels with
            this record.
        error (str | None): Stored value named ``error`` that travels with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    document_id: str
    source_id: str
    url: str
    title: str | None = None
    published_at: str | None = None
    extracted_text: str = ""
    extraction_method: str = ""
    extraction_quality: str = "unknown"
    page_count: int | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class CleanDocument(SerializableRecord):
    """Represent the ``CleanDocument`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        clean_text (str): Stored value named ``clean_text`` that travels with this
            record.
        cleaning_method (str): Stored value named ``cleaning_method`` that travels with
            this record.
        word_count (int): Stored value named ``word_count`` that travels with this
            record.
        language (str | None): Stored value named ``language`` that travels with this
            record.
        quality_flags (list[str]): Stored value named ``quality_flags`` that travels
            with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    document_id: str
    clean_text: str
    cleaning_method: str
    word_count: int
    language: str | None = None
    quality_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RedactedDocument(SerializableRecord):
    """Represent the ``RedactedDocument`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        redacted_text (str): Stored value named ``redacted_text`` that travels with this
            record.
        redaction_method (str): Stored value named ``redaction_method`` that travels
            with this record.
        redaction_count (int): Stored value named ``redaction_count`` that travels with
            this record.
        redaction_types (list[str]): Stored value named ``redaction_types`` that travels
            with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    document_id: str
    redacted_text: str
    redaction_method: str
    redaction_count: int
    redaction_types: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Entity(SerializableRecord):
    """Represent the ``Entity`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        entity_id (str): Stored value named ``entity_id`` that travels with this record.
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        entity_type (str): Stored value named ``entity_type`` that travels with this
            record.
        entity_text (str): Stored value named ``entity_text`` that travels with this
            record.
        normalized_text (str): Stored value named ``normalized_text`` that travels with
            this record.
        evidence_excerpt (str): Stored value named ``evidence_excerpt`` that travels
            with this record.
        confidence (float | None): Stored value named ``confidence`` that travels with
            this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    entity_id: str
    document_id: str
    entity_type: str
    entity_text: str
    normalized_text: str
    evidence_excerpt: str
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Claim(SerializableRecord):
    """Represent the ``Claim`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        claim_id (str): Stored value named ``claim_id`` that travels with this record.
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        claim_text (str): Stored value named ``claim_text`` that travels with this
            record.
        claim_type (str): Stored value named ``claim_type`` that travels with this
            record.
        entities (list[dict[str, Any]]): Stored value named ``entities`` that travels
            with this record.
        evidence_excerpt (str): Stored value named ``evidence_excerpt`` that travels
            with this record.
        extraction_method (str): Stored value named ``extraction_method`` that travels
            with this record.
        confidence (float | None): Stored value named ``confidence`` that travels with
            this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    claim_id: str
    document_id: str
    claim_text: str
    claim_type: str
    entities: list[dict[str, Any]] = field(default_factory=list)
    evidence_excerpt: str = ""
    extraction_method: str = ""
    confidence: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrustScore(SerializableRecord):
    """Represent the ``TrustScore`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        claim_id (str): Stored value named ``claim_id`` that travels with this record.
        source_tier_score (float | None): Stored value named ``source_tier_score`` that
            travels with this record.
        freshness_score (float | None): Stored value named ``freshness_score`` that
            travels with this record.
        corroboration_score (float | None): Stored value named ``corroboration_score``
            that travels with this record.
        independence_score (float | None): Stored value named ``independence_score``
            that travels with this record.
        conflict_penalty (float | None): Stored value named ``conflict_penalty`` that
            travels with this record.
        final_score (float | None): Stored value named ``final_score`` that travels with
            this record.
        score_explanation (str): Stored value named ``score_explanation`` that travels
            with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    claim_id: str
    source_tier_score: float | None = None
    freshness_score: float | None = None
    corroboration_score: float | None = None
    independence_score: float | None = None
    conflict_penalty: float | None = None
    final_score: float | None = None
    score_explanation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class SourceHealth(SerializableRecord):
    """Represent the ``SourceHealth`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        run_id (str): Stable run identifier used to locate records and make logs
            reproducible.
        status (str): Stored value named ``status`` that travels with this record.
        health_score (float): Stored value named ``health_score`` that travels with this
            record.
        items_discovered (int): Stored value named ``items_discovered`` that travels
            with this record.
        access_allowed (int): Stored value named ``access_allowed`` that travels with
            this record.
        access_denied (int): Stored value named ``access_denied`` that travels with this
            record.
        documents_fetched (int): Stored value named ``documents_fetched`` that travels
            with this record.
        fetch_successes (int): Stored value named ``fetch_successes`` that travels with
            this record.
        fetch_failures (int): Stored value named ``fetch_failures`` that travels with
            this record.
        extraction_successes (int): Stored value named ``extraction_successes`` that
            travels with this record.
        extraction_failures (int): Stored value named ``extraction_failures`` that
            travels with this record.
        claims_extracted (int): Stored value named ``claims_extracted`` that travels
            with this record.
        claim_yield (float): Stored value named ``claim_yield`` that travels with this
            record.
        notes (list[str]): Stored value named ``notes`` that travels with this record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    source_id: str
    run_id: str
    status: str
    health_score: float
    items_discovered: int = 0
    access_allowed: int = 0
    access_denied: int = 0
    documents_fetched: int = 0
    fetch_successes: int = 0
    fetch_failures: int = 0
    extraction_successes: int = 0
    extraction_failures: int = 0
    claims_extracted: int = 0
    claim_yield: float = 0.0
    notes: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class RetryCandidate(SerializableRecord):
    """Represent the ``RetryCandidate`` record used by the crawler pipeline.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        candidate_id (str): Stored value named ``candidate_id`` that travels with this
            record.
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        url (str): Public URL being normalized, checked, fetched, or cited.
        reason (str): Stored value named ``reason`` that travels with this record.
        retryable (bool): Stored value named ``retryable`` that travels with this
            record.
        priority (str): Stored value named ``priority`` that travels with this record.
        item_id (str | None): Stored value named ``item_id`` that travels with this
            record.
        document_id (str | None): Stored value named ``document_id`` that travels with
            this record.
        next_action (str): Stored value named ``next_action`` that travels with this
            record.
        metadata (dict[str, Any]): Stored value named ``metadata`` that travels with
            this record.
    """
    candidate_id: str
    source_id: str
    url: str
    reason: str
    retryable: bool
    priority: str
    item_id: str | None = None
    document_id: str | None = None
    next_action: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AuditEvent(SerializableRecord):
    """Represent an analyst or API action that must be auditable.

    Audit records are intentionally separate from crawler evidence records. They
    describe who viewed or exported evidence, when the action happened, and the
    run or claim the action touched without storing raw sensitive evidence in
    the audit log itself.

    Attributes:
        event_id (str): Stable identifier for this audit event.
        event_type (str): Short action name such as ``run_selected`` or
            ``evidence_exported``.
        actor (str): Analyst, service account, or authenticated caller label.
        created_at (str): ISO-8601 timestamp for when the action was recorded.
        run_id (str | None): Run affected by the action, when applicable.
        claim_id (str | None): Claim affected by the action, when applicable.
        document_id (str | None): Document affected by the action, when
            applicable.
        source_id (str | None): Source affected by the action, when applicable.
        request_path (str | None): API path that recorded the event.
        metadata (dict[str, Any]): Small JSON-safe details such as filter values
            or exported record counts.
    """

    event_id: str
    event_type: str
    actor: str
    created_at: str
    run_id: str | None = None
    claim_id: str | None = None
    document_id: str | None = None
    source_id: str | None = None
    request_path: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClaimReview(SerializableRecord):
    """Represent a human analyst decision for one extracted claim.

    Review records are append-only and live beside crawler records instead of
    replacing them. That keeps the original extracted claim immutable while
    allowing due-diligence reviewers to add status and notes over time.

    Attributes:
        review_id (str): Stable identifier for this review event.
        run_id (str): Run containing the reviewed claim.
        claim_id (str): Claim receiving the human review decision.
        review_status (str): One of ``confirmed``, ``rejected``,
            ``needs_review``, or ``watchlisted``.
        reviewer (str): Analyst or service account that made the decision.
        reviewed_at (str): ISO-8601 timestamp for the decision.
        notes (str): Analyst notes stored separately from extracted evidence.
        source_id (str | None): Source related to the claim, when available.
        document_id (str | None): Document related to the claim, when available.
        metadata (dict[str, Any]): Small safe details such as prior status.
    """

    review_id: str
    run_id: str
    claim_id: str
    review_status: str
    reviewer: str
    reviewed_at: str
    notes: str = ""
    source_id: str | None = None
    document_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IncrementalFetch(SerializableRecord):
    """Represent how one fetched URL changed compared with a previous run.

    Incremental records make scheduled crawls auditable. They separate new,
    changed, unchanged, failed, and skipped URLs so later stages can avoid
    duplicating claims for unchanged content while still showing operators what
    happened during the monitoring cycle.

    Attributes:
        incremental_id (str): Stable identifier for this run/document comparison.
        run_id (str): Current run identifier.
        source_id (str): Source that produced the URL.
        url (str): Public URL being compared.
        document_id (str): Current fetched document ID.
        status (str): One of ``new``, ``changed``, ``unchanged``, ``failed``, or
            ``skipped``.
        current_checksum (str | None): Current content checksum.
        previous_run_id (str | None): Previous run used for comparison.
        previous_document_id (str | None): Previous document ID for this URL.
        previous_checksum (str | None): Previous content checksum.
        reason (str): Short explanation for the status.
        metadata (dict[str, Any]): Extra safe details such as status code,
            content validators, or fetch errors.
    """

    incremental_id: str
    run_id: str
    source_id: str
    url: str
    document_id: str
    status: str
    current_checksum: str | None = None
    previous_run_id: str | None = None
    previous_document_id: str | None = None
    previous_checksum: str | None = None
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ClaimCluster(SerializableRecord):
    """Represent corroboration or contradiction across related claims.

    Claim clusters promote isolated extracted claims into cross-source
    intelligence. The cluster keeps each original claim intact while recording
    whether independent sources appear to support the same point or whether the
    evidence contains visible disagreement.

    Attributes:
        cluster_id (str): Stable identifier for this related-claim cluster.
        claim_type (str): Claim type shared by the grouped claims.
        status (str): ``single_source``, ``corroborated``, or ``conflicted``.
        claim_ids (list[str]): Claims included in the cluster.
        conflicting_claim_ids (list[str]): Claims whose wording appears to
            contradict the cluster.
        document_ids (list[str]): Documents represented by the cluster.
        source_ids (list[str]): Sources represented by the cluster.
        entity_keys (list[str]): Normalized entities used to group the claims.
        corroborating_source_count (int): Number of distinct sources in the
            cluster.
        independent_publisher_count (int): Number of distinct publisher types in
            the cluster.
        summary (str): Analyst-readable explanation of the agreement state.
        metadata (dict[str, Any]): Additional safe diagnostics for the grouping
            rules.
    """

    cluster_id: str
    claim_type: str
    status: str
    claim_ids: list[str] = field(default_factory=list)
    conflicting_claim_ids: list[str] = field(default_factory=list)
    document_ids: list[str] = field(default_factory=list)
    source_ids: list[str] = field(default_factory=list)
    entity_keys: list[str] = field(default_factory=list)
    corroborating_source_count: int = 0
    independent_publisher_count: int = 0
    summary: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
