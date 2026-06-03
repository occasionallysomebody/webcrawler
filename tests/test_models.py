import json

from crawler.models import (
    Claim,
    CleanDocument,
    CrawlRun,
    DiscoveredItem,
    Entity,
    ExtractedDocument,
    FetchedDocument,
    RedactedDocument,
    RetryCandidate,
    Source,
    SourceHealth,
    TrustScore,
)


def test_pipeline_models_serialize_to_json() -> None:
    records = [
        Source(
            source_id="example-source",
            name="Example Source",
            tier="tier_1",
            publisher_type="reference",
            base_url="https://example.org/",
            access_method="sitemap",
        ),
        CrawlRun(run_id="run-001", started_at="2026-06-03T05:10:00Z"),
        DiscoveredItem(
            item_id="item-001",
            source_id="example-source",
            url="https://example.com/report",
            discovery_method="manual_seed",
            discovered_at="2026-06-03T05:11:00Z",
        ),
        FetchedDocument(
            document_id="doc-001",
            source_id="example-source",
            url="https://example.com/report",
        ),
        ExtractedDocument(
            document_id="doc-001",
            source_id="example-source",
            url="https://example.com/report",
            extracted_text="Example extracted text.",
        ),
        CleanDocument(
            document_id="doc-001",
            clean_text="Example cleaned text.",
            cleaning_method="normalize_whitespace",
            word_count=3,
        ),
        RedactedDocument(
            document_id="doc-001",
            redacted_text="Example redacted text.",
            redaction_method="regex_redaction_v1",
            redaction_count=0,
        ),
        Entity(
            entity_id="entity-001",
            document_id="doc-001",
            entity_type="organization",
            entity_text="Example Organization",
            normalized_text="example organization",
            evidence_excerpt="Example Organization issued a report.",
            confidence=0.9,
        ),
        Claim(
            claim_id="claim-001",
            document_id="doc-001",
            claim_text="Example claim.",
            claim_type="risk_note",
        ),
        TrustScore(claim_id="claim-001", final_score=0.75),
        SourceHealth(
            source_id="example-source",
            run_id="run-001",
            status="healthy",
            health_score=0.8,
        ),
        RetryCandidate(
            candidate_id="frontier-001",
            source_id="example-source",
            url="https://example.com/report",
            reason="fetch_error:url_error",
            retryable=True,
            priority="high",
        ),
    ]

    for record in records:
        payload = json.loads(record.to_json())
        assert isinstance(payload, dict)
        assert payload
