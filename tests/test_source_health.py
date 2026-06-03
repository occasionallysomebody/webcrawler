from crawler.models import (
    AccessDecision,
    Claim,
    DiscoveredItem,
    ExtractedDocument,
    FetchedDocument,
    Source,
)
from crawler.source_health import assess_source_health


def source(source_id: str = "alpha") -> Source:
    return Source(
        source_id,
        "Alpha Source",
        "tier_1",
        "multilateral",
        "https://alpha.example",
        "manual_seed",
    )


def item(source_id: str = "alpha") -> DiscoveredItem:
    return DiscoveredItem(
        "item-1",
        source_id,
        "https://alpha.example/report",
        "manual_seed",
        "2026-06-03T00:00:00+00:00",
    )


def test_assess_source_health_marks_high_value_source() -> None:
    health, retry_candidates = assess_source_health(
        run_id="run-1",
        sources=[source()],
        discovered_items=[item()],
        access_decisions=[
            AccessDecision(
                "item-1",
                "alpha",
                "https://alpha.example/report",
                True,
                "allowed",
                "2026-06-03T00:00:01+00:00",
            )
        ],
        fetched_documents=[
            FetchedDocument(
                "doc-1",
                "alpha",
                "https://alpha.example/report",
                status_code=200,
            )
        ],
        extracted_documents=[
            ExtractedDocument(
                "doc-1",
                "alpha",
                "https://alpha.example/report",
                extraction_quality="high",
            )
        ],
        claims=[
            Claim("claim-1", "doc-1", "Gas flaring was reported.", "environmental_risk"),
            Claim("claim-2", "doc-1", "Methane emissions were reported.", "environmental_risk"),
            Claim("claim-3", "doc-1", "Oil pollution was reported.", "environmental_risk"),
        ],
    )

    assert retry_candidates == []
    assert health[0].status == "high_value"
    assert health[0].health_score == 1.0
    assert health[0].claim_yield == 3.0


def test_assess_source_health_splits_retryable_and_permanent_candidates() -> None:
    health, retry_candidates = assess_source_health(
        run_id="run-1",
        sources=[source()],
        discovered_items=[item()],
        access_decisions=[
            AccessDecision(
                "item-1",
                "alpha",
                "https://alpha.example/report",
                False,
                "robots_required_but_not_loaded",
                "2026-06-03T00:00:01+00:00",
            )
        ],
        fetched_documents=[
            FetchedDocument(
                "doc-1",
                "alpha",
                "https://alpha.example/report",
                fetch_error="url_error:timed out",
            ),
            FetchedDocument(
                "doc-2",
                "alpha",
                "https://alpha.example/report.pdf",
                status_code=200,
            ),
        ],
        extracted_documents=[
            ExtractedDocument(
                "doc-2",
                "alpha",
                "https://alpha.example/report.pdf",
                extraction_quality="failed",
                error="pdf_extraction_not_configured",
            )
        ],
        claims=[],
    )

    assert health[0].status == "blocked"
    assert health[0].fetch_failures == 1
    assert health[0].extraction_failures == 1
    assert {candidate.next_action for candidate in retry_candidates} == {
        "retry_robots_lookup",
        "retry_fetch",
        "configure_extractor",
    }
    assert sum(candidate.retryable for candidate in retry_candidates) == 2
