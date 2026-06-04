from crawler.models import Claim, ClaimCluster, Source
from crawler.trust import (
    conflict_penalty,
    freshness_score,
    score_claim,
    score_claims,
    trust_log_entry,
)


def source(source_id: str, tier: str, publisher_type: str) -> Source:
    return Source(
        source_id=source_id,
        name=source_id,
        tier=tier,
        publisher_type=publisher_type,
        base_url=f"https://{source_id}.example",
        access_method="manual_seed",
    )


def claim(
    claim_id: str = "claim-001",
    text: str = "Methane emissions were reported in 2025.",
    year: str = "2025",
) -> Claim:
    return Claim(
        claim_id=claim_id,
        document_id="doc-001",
        claim_text=text,
        claim_type="environmental_risk",
        entities=[
            {
                "entity_type": "date",
                "normalized_text": year,
            },
        ],
        evidence_excerpt=text,
        extraction_method="regex_dictionary_v1",
        confidence=0.7,
    )


def test_score_claim_combines_explainable_components() -> None:
    score = score_claim(
        claim(),
        source=source("world-bank", "tier_1", "multilateral"),
        corroborating_sources=[
            source("ngo", "tier_3", "ngo"),
            source("company", "tier_2", "company"),
        ],
        as_of_year=2026,
    )

    assert score.source_tier_score == 0.95
    assert score.freshness_score == 0.9
    assert score.corroboration_score == 0.75
    assert score.independence_score == 0.9
    assert score.conflict_penalty == 0
    assert score.final_score == 0.855
    assert "tier=" in score.score_explanation
    assert score.metadata["corroborating_source_count"] == 2


def test_score_claim_applies_conflict_penalty_and_missing_source_uncertainty() -> None:
    score = score_claim(
        claim(),
        conflicting_claims=[
            claim("claim-conflict-1", "Conflicting report."),
            claim("claim-conflict-2", "Another conflicting report."),
        ],
        as_of_year=2026,
    )

    assert score.source_tier_score == 0.3
    assert score.conflict_penalty == 0.3
    assert score.final_score < 0.4


def test_freshness_score_handles_missing_and_stale_dates() -> None:
    assert freshness_score(claim(text="No date included."), as_of_year=2026) == 0.9
    no_date = Claim(
        claim_id="claim-no-date",
        document_id="doc-001",
        claim_text="No date included.",
        claim_type="context",
    )
    assert freshness_score(no_date, as_of_year=2026) == 0.4
    assert (
        freshness_score(claim(text="Published in 2018.", year="2018"), as_of_year=2026)
        == 0.3
    )


def test_score_claims_and_log_entries() -> None:
    scores = score_claims(
        [claim("claim-a"), claim("claim-b")],
        sources_by_claim_id={
            "claim-a": source("src-a", "tier_2", "government"),
        },
    )

    assert len(scores) == 2
    assert scores[0].source_tier_score == 0.8
    assert scores[1].source_tier_score == 0.3
    assert trust_log_entry(scores[0])["stage"] == "score_trust"
    assert conflict_penalty([claim("a"), claim("b"), claim("c"), claim("d")]) == 0.5


def test_score_claims_uses_corroboration_clusters() -> None:
    claims = [claim("claim-a"), claim("claim-b")]
    cluster = ClaimCluster(
        cluster_id="cluster-1",
        claim_type="environmental_risk",
        status="corroborated",
        claim_ids=["claim-a", "claim-b"],
        source_ids=["src-a", "src-b"],
        corroborating_source_count=2,
        independent_publisher_count=2,
    )

    scores = score_claims(
        claims,
        sources_by_claim_id={
            "claim-a": source("src-a", "tier_2", "government"),
            "claim-b": source("src-b", "tier_3", "ngo"),
        },
        claim_clusters=[cluster],
    )

    assert scores[0].corroboration_score == 0.5
    assert scores[0].independence_score == 0.65
    assert scores[0].metadata["corroboration_status"] == "corroborated"
