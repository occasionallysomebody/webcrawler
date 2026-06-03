import json

from crawler.models import (
    Claim,
    CleanDocument,
    CrawlRun,
    DiscoveredItem,
    ExtractedDocument,
    FetchedDocument,
    Source,
    TrustScore,
)


def test_pipeline_models_serialize_to_json() -> None:
    records = [
        Source(
            source_id="world-bank",
            name="World Bank",
            tier="tier_1",
            publisher_type="multilateral",
            base_url="https://www.worldbank.org/",
            access_method="sitemap",
        ),
        CrawlRun(run_id="run-001", started_at="2026-06-03T05:10:00Z"),
        DiscoveredItem(
            item_id="item-001",
            source_id="world-bank",
            url="https://example.com/report",
            discovery_method="manual_seed",
            discovered_at="2026-06-03T05:11:00Z",
        ),
        FetchedDocument(
            document_id="doc-001",
            source_id="world-bank",
            url="https://example.com/report",
        ),
        ExtractedDocument(
            document_id="doc-001",
            source_id="world-bank",
            url="https://example.com/report",
            extracted_text="Example extracted text.",
        ),
        CleanDocument(
            document_id="doc-001",
            clean_text="Example cleaned text.",
            cleaning_method="normalize_whitespace",
            word_count=3,
        ),
        Claim(
            claim_id="claim-001",
            document_id="doc-001",
            claim_text="Example claim.",
            claim_type="risk_note",
        ),
        TrustScore(claim_id="claim-001", final_score=0.75),
    ]

    for record in records:
        payload = json.loads(record.to_json())
        assert isinstance(payload, dict)
        assert payload
