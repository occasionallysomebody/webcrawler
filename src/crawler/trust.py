"""Explainable trust scoring for extracted claims.

Trust scores combine simple signals such as source tier, freshness,
corroboration, independence, and conflict penalties. The formulas are small on
purpose so analysts can understand why a claim received a given confidence.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
import re

from crawler.corroboration import claims_by_cluster
from crawler.models import Claim, ClaimCluster, Source, TrustScore


TIER_SCORES = {
    "tier_1": 0.95,
    "tier_2": 0.8,
    "tier_3": 0.65,
    "tier_4": 0.55,
}


def score_claim(
    claim: Claim,
    *,
    source: Source | None = None,
    corroborating_sources: Iterable[Source] = (),
    conflicting_claims: Iterable[Claim] = (),
    as_of_year: int | None = None,
) -> TrustScore:
    """Score one claim with explainable deterministic components."""
    corroborators = list(corroborating_sources)
    conflicts = list(conflicting_claims)
    tier_score = source_tier_score(source)
    fresh_score = freshness_score(claim, as_of_year=as_of_year)
    corr_score = corroboration_score(corroborators)
    indep_score = independence_score(source, corroborators)
    penalty = conflict_penalty(conflicts)
    extraction_score = claim.confidence if claim.confidence is not None else 0.5

    final = (
        0.30 * tier_score
        + 0.20 * fresh_score
        + 0.20 * corr_score
        + 0.15 * indep_score
        + 0.15 * extraction_score
        - penalty
    )
    final = round(_clamp(final), 3)

    return TrustScore(
        claim_id=claim.claim_id,
        source_tier_score=round(tier_score, 3),
        freshness_score=round(fresh_score, 3),
        corroboration_score=round(corr_score, 3),
        independence_score=round(indep_score, 3),
        conflict_penalty=round(penalty, 3),
        final_score=final,
        score_explanation=(
            f"tier={tier_score:.2f}; freshness={fresh_score:.2f}; "
            f"corroboration={corr_score:.2f}; independence={indep_score:.2f}; "
            f"extraction={extraction_score:.2f}; conflicts={len(conflicts)}"
        ),
        metadata={
            "scoring_method": "deterministic_trust_v1",
            "source_id": source.source_id if source else None,
            "publisher_type": source.publisher_type if source else None,
            "corroborating_source_count": len(corroborators),
            "conflicting_claim_count": len(conflicts),
        },
    )


def score_claims(
    claims: Iterable[Claim],
    *,
    sources_by_claim_id: dict[str, Source] | None = None,
    claim_clusters: Iterable[ClaimCluster] = (),
) -> list[TrustScore]:
    """Score many claims with optional source context."""
    source_map = sources_by_claim_id or {}
    claim_list = list(claims)
    claim_by_id = {claim.claim_id: claim for claim in claim_list}
    cluster_by_claim = claims_by_cluster(list(claim_clusters))
    scores = []
    for claim in claim_list:
        cluster = cluster_by_claim.get(claim.claim_id)
        corroborating_sources = []
        conflicting_claims = []
        if cluster is not None:
            for other_claim_id in cluster.claim_ids:
                if other_claim_id == claim.claim_id:
                    continue
                source = source_map.get(other_claim_id)
                if source is not None:
                    corroborating_sources.append(source)
            conflicting_claims = [
                claim_by_id[claim_id]
                for claim_id in cluster.conflicting_claim_ids
                if claim_id in claim_by_id and claim_id != claim.claim_id
            ]
        score = score_claim(
            claim,
            source=source_map.get(claim.claim_id),
            corroborating_sources=corroborating_sources,
            conflicting_claims=conflicting_claims,
        )
        if cluster is not None:
            score.metadata = {
                **score.metadata,
                "corroboration_cluster_id": cluster.cluster_id,
                "corroboration_status": cluster.status,
                "corroborating_claim_ids": [
                    claim_id for claim_id in cluster.claim_ids if claim_id != claim.claim_id
                ],
                "conflicting_claim_ids": [
                    claim_id
                    for claim_id in cluster.conflicting_claim_ids
                    if claim_id != claim.claim_id
                ],
            }
        scores.append(score)
    return scores


def source_tier_score(source: Source | None) -> float:
    """Return an explainable source-tier component."""
    if source is None:
        return 0.3
    return TIER_SCORES.get(source.tier.lower(), 0.4)


def freshness_score(claim: Claim, *, as_of_year: int | None = None) -> float:
    """Score freshness from year entities or year-like claim text."""
    year = _latest_year(claim)
    if year is None:
        return 0.4
    current_year = as_of_year or datetime.now(UTC).year
    age = max(0, current_year - year)
    if age <= 1:
        return 0.9
    if age <= 3:
        return 0.7
    if age <= 5:
        return 0.5
    return 0.3


def corroboration_score(sources: Iterable[Source]) -> float:
    """Score corroboration count with diminishing returns."""
    count = len(list(sources))
    if count == 0:
        return 0.2
    if count == 1:
        return 0.5
    if count == 2:
        return 0.75
    return 0.95


def independence_score(
    source: Source | None,
    corroborating_sources: Iterable[Source],
) -> float:
    """Score diversity of publisher types."""
    publisher_types = {
        item.publisher_type
        for item in ([source] if source else []) + list(corroborating_sources)
        if item is not None and item.publisher_type
    }
    count = len(publisher_types)
    if count == 0:
        return 0.2
    if count == 1:
        return 0.35
    if count == 2:
        return 0.65
    return 0.9


def conflict_penalty(conflicting_claims: Iterable[Claim]) -> float:
    """Return visible penalty for conflicts without hiding evidence."""
    return min(0.5, 0.15 * len(list(conflicting_claims)))


def trust_log_entry(score: TrustScore) -> dict[str, object]:
    """Create a structured log entry for trust scoring output."""
    return {
        "stage": "score_trust",
        "claim_id": score.claim_id,
        "final_score": score.final_score,
        "conflict_penalty": score.conflict_penalty,
        "scoring_method": score.metadata.get("scoring_method"),
    }


def _latest_year(claim: Claim) -> int | None:
    """Support the module's public workflow by computing latest year.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        claim (Claim): Claim record whose evidence, score, or display data is being
            computed.
    
    Returns:
        int | None: Result produced for the next pipeline step or caller.
    """
    years: list[int] = []
    for entity in claim.entities:
        if entity.get("entity_type") == "date":
            years.extend(_years(str(entity.get("normalized_text", ""))))
    years.extend(_years(claim.claim_text))
    return max(years) if years else None


def _years(text: str) -> list[int]:
    """Support the module's public workflow by computing years.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        text (str): Text content being parsed, cleaned, redacted, or searched.
    
    Returns:
        list[int]: Result produced for the next pipeline step or caller.
    """
    return [int(match) for match in re.findall(r"\b(?:19|20)\d{2}\b", text)]


def _clamp(value: float) -> float:
    """Support the module's public workflow by computing clamp.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        value (float): Raw value being normalized or converted into a typed
            representation.
    
    Returns:
        float: Normalized score between 0 and 1 unless the function description says
            otherwise.
    """
    return max(0.0, min(1.0, value))
