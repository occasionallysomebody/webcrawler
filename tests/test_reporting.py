from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.models import Claim, FetchedDocument, Source, TrustScore
from crawler.reporting import (
    generate_markdown_report,
    reporting_log_entry,
    write_markdown_report,
)


def test_generate_markdown_report_cites_sources_and_confidence() -> None:
    markdown = generate_markdown_report(
        title="Azerbaijan Energy Signals",
        question="What environmental risks appeared?",
        claims=[
            Claim(
                claim_id="claim-1",
                document_id="doc-1",
                claim_text="Gas flaring pollution was reported.",
                claim_type="environmental_risk",
                evidence_excerpt="Gas flaring pollution was reported near the terminal.",
                confidence=0.7,
            ),
        ],
        trust_scores=[
            TrustScore(
                claim_id="claim-1",
                final_score=0.812,
                score_explanation="tier=0.95; freshness=0.90",
            ),
        ],
        documents=[
            FetchedDocument(
                document_id="doc-1",
                source_id="source-1",
                url="https://example.org/report",
                final_url="https://example.org/final",
                retrieved_at="2026-06-03T00:00:00+00:00",
            ),
        ],
        sources=[
            Source(
                "source-1",
                "Example Source",
                "tier_1",
                "multilateral",
                "https://example.org",
                "manual_seed",
            ),
        ],
        known_gaps=["Only one source supplied."],
    )

    assert "# Azerbaijan Energy Signals" in markdown
    assert "## Evidence Summary" in markdown
    assert "Confidence: 0.812" in markdown
    assert "Example Source: https://example.org/final" in markdown
    assert "## Interpretation" in markdown
    assert "- Only one source supplied." in markdown


def test_generate_markdown_report_handles_missing_inputs() -> None:
    markdown = generate_markdown_report(title="Empty Report", claims=[])

    assert "No claims were available for reporting." in markdown
    assert "No source documents were supplied." in markdown
    assert "No known gaps were supplied." in markdown


def test_write_markdown_report_and_log_entry() -> None:
    with TemporaryDirectory() as tmp_dir:
        path = write_markdown_report(
            Path(tmp_dir) / "reports" / "report.md",
            "# Report\n",
        )
        content = path.read_text(encoding="utf-8")

    assert content == "# Report\n"
    assert reporting_log_entry(path, claim_count=2) == {
        "stage": "generate_report",
        "output_path": str(path),
        "format": "markdown",
        "claim_count": 2,
    }
