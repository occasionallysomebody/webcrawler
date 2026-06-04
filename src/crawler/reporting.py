"""Markdown reporting for cited crawler outputs.

Reports turn extracted claims and trust scores into human-readable analyst
briefs. This module keeps citation formatting explicit so a reader can move from
a summary sentence back to the source URL and confidence explanation.
"""

from __future__ import annotations

from pathlib import Path

from crawler.models import Claim, FetchedDocument, Source, TrustScore


def generate_markdown_report(
    *,
    title: str,
    claims: list[Claim],
    trust_scores: list[TrustScore] | None = None,
    documents: list[FetchedDocument] | None = None,
    sources: list[Source] | None = None,
    question: str | None = None,
    known_gaps: list[str] | None = None,
) -> str:
    """Generate a cited Markdown report from pipeline records."""
    score_by_claim = {score.claim_id: score for score in trust_scores or []}
    doc_by_id = {document.document_id: document for document in documents or []}
    source_by_id = {source.source_id: source for source in sources or []}
    gaps = known_gaps or []

    lines = [f"# {title}", ""]
    if question:
        lines.extend(["## Question Answered", "", question, ""])

    lines.extend(["## Evidence Summary", ""])
    if not claims:
        lines.extend(["No claims were available for reporting.", ""])
    for index, claim in enumerate(claims, start=1):
        score = score_by_claim.get(claim.claim_id)
        document = doc_by_id.get(claim.document_id)
        source = source_by_id.get(document.source_id) if document else None
        citation = _citation(document, source)
        confidence = _confidence(score, claim)

        lines.extend(
            [
                f"### Claim {index}",
                "",
                f"- Claim: {claim.claim_text}",
                f"- Type: {claim.claim_type}",
                f"- Confidence: {confidence}",
                f"- Source agreement: {_agreement(claim)}",
                f"- Citation: {citation}",
                f"- Evidence excerpt: {claim.evidence_excerpt or 'Not available.'}",
                "",
            ],
        )

    lines.extend(["## Interpretation", ""])
    if claims:
        lines.append(
            "The claims above are extracted signals from public-source records. "
            "They should be reviewed against the cited evidence before use in "
            "business, safety, compliance, or policy decisions.",
        )
    else:
        lines.append("No interpretation is provided because no claims were supplied.")
    lines.append("")

    lines.extend(["## Known Gaps", ""])
    if gaps:
        lines.extend(f"- {gap}" for gap in gaps)
    else:
        lines.append("- No known gaps were supplied.")
    lines.append("")

    lines.extend(["## Sources Used", ""])
    if documents:
        for document in documents:
            source = source_by_id.get(document.source_id)
            lines.append(f"- {_citation(document, source)}")
    else:
        lines.append("- No source documents were supplied.")
    lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def write_markdown_report(path: str | Path, markdown: str) -> Path:
    """Write a Markdown report and return the output path."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(markdown, encoding="utf-8")
    return target


def reporting_log_entry(path: str | Path, *, claim_count: int) -> dict[str, object]:
    """Create a structured log entry for report generation."""
    return {
        "stage": "generate_report",
        "output_path": str(path),
        "format": "markdown",
        "claim_count": claim_count,
    }


def _citation(document: FetchedDocument | None, source: Source | None) -> str:
    """Support the module's public workflow by computing citation.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        document (FetchedDocument | None): Document record being transformed by this
            helper.
        source (Source | None): Source registry entry that explains where a document or
            URL came from.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    if document is None:
        return "Missing document metadata."
    label = source.name if source else document.source_id
    url = document.final_url or document.url
    retrieved = f", retrieved {document.retrieved_at}" if document.retrieved_at else ""
    return f"{label}: {url}{retrieved}"


def _confidence(score: TrustScore | None, claim: Claim) -> str:
    """Support the module's public workflow by computing confidence.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        score (TrustScore | None): Trust score or numeric value being converted into
            output data.
        claim (Claim): Claim record whose evidence, score, or display data is being
            computed.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    if score and score.final_score is not None:
        return f"{score.final_score:.3f} ({score.score_explanation})"
    if claim.confidence is not None:
        return f"{claim.confidence:.3f} (claim extraction confidence only)"
    return "Unknown"


def _agreement(claim: Claim) -> str:
    """Return source agreement context for a claim.

    Args:
        claim (Claim): Claim record whose corroboration metadata may be shown.

    Returns:
        str: Human-readable agreement or conflict summary.
    """

    status = claim.metadata.get("corroboration_status")
    summary = claim.metadata.get("corroboration_summary")
    if status and summary:
        return f"{status}: {summary}"
    return "Not assessed."
