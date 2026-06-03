"""Stable pipeline record definitions."""

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
        return _normalize(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


@dataclass(slots=True)
class Source(SerializableRecord):
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
class FetchedDocument(SerializableRecord):
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
    document_id: str
    clean_text: str
    cleaning_method: str
    word_count: int
    language: str | None = None
    quality_flags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Claim(SerializableRecord):
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
    claim_id: str
    source_tier_score: float | None = None
    freshness_score: float | None = None
    corroboration_score: float | None = None
    independence_score: float | None = None
    conflict_penalty: float | None = None
    final_score: float | None = None
    score_explanation: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
