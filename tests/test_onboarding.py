from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.onboarding import (
    OnboardingError,
    load_proposed_sources,
    onboarding_log_entry,
    promote_approved_sources,
    write_proposed_source_template,
)
from crawler.source_registry import load_source_registry


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_proposed_sources_keeps_status_separate_from_active_registry() -> None:
    proposals = load_proposed_sources(FIXTURES / "proposed_sources.csv")

    assert [proposal.source.source_id for proposal in proposals] == [
        "new-approved",
        "new-pending",
        "new-rejected",
    ]
    assert [proposal.proposal_status for proposal in proposals] == [
        "approved",
        "proposed",
        "rejected",
    ]


def test_load_proposed_sources_rejects_unsafe_approved_rows() -> None:
    try:
        load_proposed_sources(FIXTURES / "proposed_sources_invalid.csv")
    except OnboardingError as error:
        fields = {(issue.source_id, issue.field) for issue in error.issues}
        assert ("bad-approved", "reviewed_by") in fields
        assert ("bad-approved", "access_method") in fields
        assert ("bad-approved", "rate_limit_seconds") in fields
    else:
        raise AssertionError("expected OnboardingError")


def test_promote_approved_sources_writes_only_approved_to_active_registry() -> None:
    active_csv = "\n".join(
        [
            "source_id,name,tier,publisher_type,base_url,access_method,"
            "rate_limit_seconds,robots_required,enabled,notes,sitemap_url,rss_url,"
            "api_url,allowed_paths,blocked_paths,language,country,domain_tags,"
            "known_bias_or_limitation",
            "existing,Existing Source,tier_1,multilateral,https://existing.example,"
            "public_html,2,true,true,Existing.,,,,,,en,Azerbaijan,baseline,",
        ]
    )
    with TemporaryDirectory() as tmp_dir:
        active_path = Path(tmp_dir) / "sources.csv"
        active_path.write_text(active_csv, encoding="utf-8")
        report = promote_approved_sources(
            proposed_path=FIXTURES / "proposed_sources.csv",
            active_path=active_path,
        )
        registry = load_source_registry(active_path)

    assert report.promoted_count == 1
    assert report.approved_count == 1
    assert report.pending_count == 1
    assert report.rejected_count == 1
    assert [source.source_id for source in registry.sources] == [
        "existing",
        "new-approved",
    ]
    assert registry.sources[1].metadata["sitemap_url"] == "https://approved.example/sitemap.xml"
    assert "Onboarding review" in registry.sources[1].notes


def test_promote_approved_sources_skips_existing_ids() -> None:
    active_csv = (FIXTURES / "proposed_sources.csv").read_text(encoding="utf-8")
    with TemporaryDirectory() as tmp_dir:
        active_path = Path(tmp_dir) / "sources.csv"
        active_path.write_text(active_csv, encoding="utf-8")
        report = promote_approved_sources(
            proposed_path=FIXTURES / "proposed_sources.csv",
            active_path=active_path,
        )

    assert report.promoted_count == 0
    assert report.skipped_existing == ["new-approved"]
    assert onboarding_log_entry(report)["stage"] == "source_onboarding"


def test_write_proposed_source_template() -> None:
    with TemporaryDirectory() as tmp_dir:
        path = write_proposed_source_template(Path(tmp_dir) / "proposed.csv")
        header = path.read_text(encoding="utf-8").splitlines()[0]

    assert "proposal_status" in header
    assert "review_notes" in header
