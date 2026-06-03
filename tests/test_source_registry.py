from pathlib import Path

from crawler.source_registry import SourceRegistryError, load_source_registry


FIXTURES = Path(__file__).parent / "fixtures"


def test_load_source_registry_skips_disabled_sources() -> None:
    registry = load_source_registry(FIXTURES / "sources_valid.csv")

    assert [source.source_id for source in registry.sources] == ["alpha"]
    assert [source.source_id for source in registry.skipped] == ["beta"]
    assert registry.sources[0].rate_limit_seconds == 1.5
    assert registry.sources[0].robots_required is True
    assert registry.sources[0].allowed_paths == ["/reports", "/data"]
    assert registry.sources[0].blocked_paths == ["/private"]
    assert registry.sources[0].metadata["sitemap_url"] == "https://alpha.example/sitemap.xml"
    assert registry.sources[0].metadata["domain_tags"] == ["baseline", "reports"]


def test_load_source_registry_can_include_disabled_sources() -> None:
    registry = load_source_registry(
        FIXTURES / "sources_valid.csv",
        include_disabled=True,
    )

    assert [source.source_id for source in registry.sources] == ["alpha", "beta"]
    assert registry.skipped == []


def test_load_source_registry_reports_invalid_rows() -> None:
    try:
        load_source_registry(FIXTURES / "sources_invalid.csv")
    except SourceRegistryError as error:
        fields = {(issue.row_number, issue.field) for issue in error.issues}
        assert (2, "base_url") in fields
        assert (3, "robots_required") in fields
    else:
        raise AssertionError("expected SourceRegistryError")
