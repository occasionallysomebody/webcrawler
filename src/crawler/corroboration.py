"""Corroboration and contradiction detection for extracted claims.

The first implementation uses transparent local rules. It groups claims by
claim type and shared entities, then flags visible disagreement when related
claims contain simple negation or opposing trend language. This keeps the output
auditable before adding heavier NLP or paid services.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import re

from crawler.models import Claim, ClaimCluster, FetchedDocument, Source


ENTITY_TYPES_FOR_GROUPING = {"organization", "asset", "location", "risk_topic"}
NEGATION_TERMS = {
    "no",
    "not",
    "without",
    "denied",
    "denies",
    "deny",
    "unsubstantiated",
    "no evidence",
}
INCREASE_TERMS = {"increase", "increased", "rising", "rose", "higher", "growth"}
DECREASE_TERMS = {"decrease", "decreased", "falling", "fell", "lower", "decline"}


def cluster_claims(
    claims: list[Claim],
    *,
    documents_by_id: dict[str, FetchedDocument] | None = None,
    sources_by_id: dict[str, Source] | None = None,
) -> list[ClaimCluster]:
    """Group similar claims and flag source agreement or disagreement.

    Args:
        claims (list[Claim]): Extracted claims to compare.
        documents_by_id (dict[str, FetchedDocument] | None): Documents keyed by
            document ID for source lookup.
        sources_by_id (dict[str, Source] | None): Sources keyed by source ID for
            publisher-type independence checks.

    Returns:
        list[ClaimCluster]: Corroboration clusters sorted by cluster ID.
    """

    documents = documents_by_id or {}
    sources = sources_by_id or {}
    grouped: dict[tuple[str, tuple[str, ...]], list[Claim]] = defaultdict(list)
    for claim in claims:
        grouped[_cluster_key(claim)].append(claim)

    clusters = []
    for key, group_claims in grouped.items():
        claim_type, entity_keys = key
        source_ids = _source_ids(group_claims, documents)
        publisher_types = _publisher_types(source_ids, sources)
        conflicting_ids = _conflicting_claim_ids(group_claims)
        status = _cluster_status(source_ids, publisher_types, conflicting_ids)
        cluster_id = _stable_id("cluster", claim_type, *entity_keys)
        clusters.append(
            ClaimCluster(
                cluster_id=cluster_id,
                claim_type=claim_type,
                status=status,
                claim_ids=sorted(claim.claim_id for claim in group_claims),
                conflicting_claim_ids=sorted(conflicting_ids),
                document_ids=sorted({claim.document_id for claim in group_claims}),
                source_ids=sorted(source_ids),
                entity_keys=list(entity_keys),
                corroborating_source_count=len(source_ids),
                independent_publisher_count=len(publisher_types),
                summary=_cluster_summary(status, len(source_ids), len(publisher_types)),
                metadata={
                    "grouping_method": "entity_claim_type_v1",
                    "polarity_by_claim_id": {
                        claim.claim_id: _claim_polarity(claim.claim_text)
                        for claim in group_claims
                    },
                },
            )
        )

    clusters.sort(key=lambda cluster: cluster.cluster_id)
    return clusters


def annotate_claims_with_clusters(
    claims: list[Claim],
    clusters: list[ClaimCluster],
) -> None:
    """Attach corroboration metadata to mutable claim records.

    Args:
        claims (list[Claim]): Claims to annotate in place.
        clusters (list[ClaimCluster]): Clusters created from the same claims.

    Returns:
        None: Claims are updated in place before JSONL persistence.
    """

    cluster_by_claim_id = {
        claim_id: cluster
        for cluster in clusters
        for claim_id in cluster.claim_ids
    }
    for claim in claims:
        cluster = cluster_by_claim_id.get(claim.claim_id)
        if cluster is None:
            continue
        claim.metadata = {
            **claim.metadata,
            "corroboration_cluster_id": cluster.cluster_id,
            "corroboration_status": cluster.status,
            "corroborating_source_count": cluster.corroborating_source_count,
            "independent_publisher_count": cluster.independent_publisher_count,
            "conflicting_claim_ids": cluster.conflicting_claim_ids,
            "corroboration_summary": cluster.summary,
        }


def claims_by_cluster(clusters: list[ClaimCluster]) -> dict[str, ClaimCluster]:
    """Return clusters keyed by claim ID.

    Args:
        clusters (list[ClaimCluster]): Corroboration clusters.

    Returns:
        dict[str, ClaimCluster]: Cluster lookup by claim ID.
    """

    return {
        claim_id: cluster
        for cluster in clusters
        for claim_id in cluster.claim_ids
    }


def corroboration_log_entry(clusters: list[ClaimCluster]) -> dict[str, object]:
    """Create a structured log entry for corroboration output.

    Args:
        clusters (list[ClaimCluster]): Corroboration clusters.

    Returns:
        dict[str, object]: JSON-safe run event.
    """

    return {
        "stage": "detect_corroboration",
        "claim_clusters": len(clusters),
        "corroborated": sum(1 for cluster in clusters if cluster.status == "corroborated"),
        "conflicted": sum(1 for cluster in clusters if cluster.status == "conflicted"),
        "single_source": sum(
            1 for cluster in clusters if cluster.status == "single_source"
        ),
    }


def _cluster_key(claim: Claim) -> tuple[str, tuple[str, ...]]:
    """Compute the deterministic grouping key for one claim.

    Args:
        claim (Claim): Claim to group.

    Returns:
        tuple[str, tuple[str, ...]]: Claim type plus normalized entity keys.
    """

    entities = sorted(
        {
            f"{entity.get('entity_type')}:{entity.get('normalized_text')}"
            for entity in claim.entities
            if entity.get("entity_type") in ENTITY_TYPES_FOR_GROUPING
            and entity.get("normalized_text")
        }
    )
    if not entities:
        entities = [_fallback_topic_key(claim.claim_text)]
    return claim.claim_type, tuple(entities[:4])


def _fallback_topic_key(text: str) -> str:
    """Build a coarse grouping key when no entities were extracted.

    Args:
        text (str): Claim text.

    Returns:
        str: Deterministic fallback key.
    """

    words = [
        word
        for word in re.findall(r"[a-z0-9]+", text.casefold())
        if len(word) > 3 and word not in {"reported", "report", "claims", "claim"}
    ]
    return "topic:" + "-".join(words[:5])


def _source_ids(
    claims: list[Claim],
    documents_by_id: dict[str, FetchedDocument],
) -> set[str]:
    """Return source IDs represented by a claim group.

    Args:
        claims (list[Claim]): Claims in a cluster candidate.
        documents_by_id (dict[str, FetchedDocument]): Documents keyed by ID.

    Returns:
        set[str]: Distinct source IDs.
    """

    source_ids = set()
    for claim in claims:
        document = documents_by_id.get(claim.document_id)
        if document is not None:
            source_ids.add(document.source_id)
    return source_ids


def _publisher_types(
    source_ids: set[str],
    sources_by_id: dict[str, Source],
) -> set[str]:
    """Return publisher types represented by a claim group.

    Args:
        source_ids (set[str]): Source IDs in the group.
        sources_by_id (dict[str, Source]): Sources keyed by source ID.

    Returns:
        set[str]: Distinct publisher types.
    """

    return {
        sources_by_id[source_id].publisher_type
        for source_id in source_ids
        if source_id in sources_by_id and sources_by_id[source_id].publisher_type
    }


def _conflicting_claim_ids(claims: list[Claim]) -> set[str]:
    """Return claim IDs that visibly conflict within a group.

    Args:
        claims (list[Claim]): Grouped claims.

    Returns:
        set[str]: Claim IDs involved in a conflict.
    """

    polarity_by_id = {
        claim.claim_id: _claim_polarity(claim.claim_text)
        for claim in claims
    }
    polarities = set(polarity_by_id.values())
    if "negative" in polarities and "positive" in polarities:
        return set(polarity_by_id)
    if "increase" in polarities and "decrease" in polarities:
        return set(polarity_by_id)
    return set()


def _claim_polarity(text: str) -> str:
    """Classify simple claim polarity for contradiction detection.

    Args:
        text (str): Claim text.

    Returns:
        str: ``positive``, ``negative``, ``increase``, ``decrease``, or
        ``neutral``.
    """

    lowered = text.casefold()
    if any(term in lowered for term in NEGATION_TERMS):
        return "negative"
    if any(term in lowered for term in DECREASE_TERMS):
        return "decrease"
    if any(term in lowered for term in INCREASE_TERMS):
        return "increase"
    return "positive"


def _cluster_status(
    source_ids: set[str],
    publisher_types: set[str],
    conflicting_ids: set[str],
) -> str:
    """Return the cluster status.

    Args:
        source_ids (set[str]): Sources represented by the cluster.
        publisher_types (set[str]): Publisher types represented by the cluster.
        conflicting_ids (set[str]): Claim IDs involved in visible disagreement.

    Returns:
        str: Cluster status.
    """

    if conflicting_ids:
        return "conflicted"
    if len(source_ids) >= 2 and len(publisher_types) >= 2:
        return "corroborated"
    return "single_source"


def _cluster_summary(status: str, source_count: int, publisher_count: int) -> str:
    """Build a short analyst-readable agreement summary.

    Args:
        status (str): Cluster status.
        source_count (int): Number of represented sources.
        publisher_count (int): Number of represented publisher types.

    Returns:
        str: Summary sentence.
    """

    if status == "conflicted":
        return "Related claims contain visible disagreement and need review."
    if status == "corroborated":
        return (
            f"Supported by {source_count} source(s) across "
            f"{publisher_count} publisher type(s)."
        )
    return "Only one source perspective is available for this claim cluster."


def _stable_id(prefix: str, *parts: str) -> str:
    """Return a stable identifier from text parts.

    Args:
        prefix (str): ID prefix.
        parts (str): Values to hash.

    Returns:
        str: Stable ID.
    """

    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"
