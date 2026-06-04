from crawler.corroboration import (
    annotate_claims_with_clusters,
    cluster_claims,
    corroboration_log_entry,
)
from crawler.models import Claim, FetchedDocument, Source


def source(source_id: str, publisher_type: str) -> Source:
    return Source(
        source_id,
        source_id,
        "tier_2",
        publisher_type,
        f"https://{source_id}.example",
        "manual_seed",
    )


def claim(claim_id: str, document_id: str, text: str) -> Claim:
    return Claim(
        claim_id=claim_id,
        document_id=document_id,
        claim_text=text,
        claim_type="environmental_risk",
        entities=[
            {"entity_type": "asset", "normalized_text": "sangachal terminal"},
            {"entity_type": "location", "normalized_text": "azerbaijan"},
        ],
        evidence_excerpt=text,
    )


def test_cluster_claims_marks_independent_corroboration() -> None:
    claims = [
        claim("claim-1", "doc-1", "Gas flaring pollution was reported in Azerbaijan."),
        claim("claim-2", "doc-2", "Gas flaring pollution was reported near Sangachal."),
    ]
    documents = {
        "doc-1": FetchedDocument("doc-1", "source-1", "https://one.example"),
        "doc-2": FetchedDocument("doc-2", "source-2", "https://two.example"),
    }
    sources = {
        "source-1": source("source-1", "ngo"),
        "source-2": source("source-2", "government"),
    }

    clusters = cluster_claims(
        claims,
        documents_by_id=documents,
        sources_by_id=sources,
    )
    annotate_claims_with_clusters(claims, clusters)

    assert len(clusters) == 1
    assert clusters[0].status == "corroborated"
    assert clusters[0].corroborating_source_count == 2
    assert clusters[0].independent_publisher_count == 2
    assert claims[0].metadata["corroboration_status"] == "corroborated"
    assert corroboration_log_entry(clusters)["corroborated"] == 1


def test_cluster_claims_flags_visible_conflicts() -> None:
    claims = [
        claim("claim-1", "doc-1", "Gas flaring pollution was reported in Azerbaijan."),
        claim("claim-2", "doc-2", "No gas flaring pollution was reported in Azerbaijan."),
    ]
    documents = {
        "doc-1": FetchedDocument("doc-1", "source-1", "https://one.example"),
        "doc-2": FetchedDocument("doc-2", "source-2", "https://two.example"),
    }
    sources = {
        "source-1": source("source-1", "ngo"),
        "source-2": source("source-2", "government"),
    }

    clusters = cluster_claims(
        claims,
        documents_by_id=documents,
        sources_by_id=sources,
    )

    assert clusters[0].status == "conflicted"
    assert clusters[0].conflicting_claim_ids == ["claim-1", "claim-2"]
    assert "visible disagreement" in clusters[0].summary
