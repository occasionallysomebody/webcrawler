from pathlib import Path

from crawler.discovery import (
    content_type_hint,
    discover_expanded_source_urls,
    discover_from_source_registry,
    discover_manual_seed_urls,
    normalize_url,
)
from crawler.models import Source


FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(self, body: str) -> None:
        self.body = body.encode("utf-8")

    def read(self) -> bytes:
        return self.body

    def close(self) -> None:
        return None


class FakeOpener:
    def __init__(self, *bodies: str) -> None:
        self.bodies = list(bodies)

    def open(self, request, timeout):
        return FakeResponse(self.bodies.pop(0))


def source(source_id: str, base_url: str, **overrides) -> Source:
    values = {
        "source_id": source_id,
        "name": f"{source_id} name",
        "tier": "tier_1",
        "publisher_type": "reference",
        "base_url": base_url,
        "access_method": "public_html",
    }
    values.update(overrides)
    return Source(**values)


def test_discover_manual_seed_urls_normalizes_and_deduplicates_urls() -> None:
    items = discover_manual_seed_urls(
        [
            source(
                "alpha",
                "HTTPS://Example.ORG:443/report.pdf#section",
                access_method="public_pdf",
            ),
            source("alpha-copy", "https://example.org/report.pdf"),
            source("beta", "https://beta.example/about"),
        ],
        discovered_at="2026-06-03T00:00:00+00:00",
    )

    assert [item.url for item in items] == [
        "https://example.org/report.pdf",
        "https://beta.example/about",
    ]
    assert items[0].source_id == "alpha"
    assert items[0].discovery_method == "manual_seed"
    assert items[0].content_type_hint == "application/pdf"
    assert items[0].metadata["duplicate_source_ids"] == ["alpha-copy"]
    assert items[1].metadata["access_method"] == "public_html"


def test_discover_from_source_registry_uses_enabled_sources_only() -> None:
    items = discover_from_source_registry(
        FIXTURES / "sources_valid.csv",
        discovered_at="2026-06-03T00:00:00+00:00",
    )

    assert len(items) == 1
    assert items[0].source_id == "alpha"
    assert items[0].url == "https://alpha.example/"


def test_normalize_url_requires_absolute_url() -> None:
    try:
        normalize_url("/relative/report")
    except ValueError as error:
        assert "absolute" in str(error)
    else:
        raise AssertionError("expected absolute URL validation error")


def test_content_type_hint_without_fetching() -> None:
    assert (
        content_type_hint(
            source("pdf", "https://example.org/report", access_method="public_pdf"),
            "https://example.org/report",
        )
        == "application/pdf"
    )
    assert (
        content_type_hint(
            source("json", "https://example.org/data.json"),
            "https://example.org/data.json",
        )
        == "application/json"
    )


def test_discover_expanded_source_urls_reads_sitemap_rss_and_api() -> None:
    sources = [
        source(
            "alpha",
            "https://alpha.example/",
            metadata={
                "sitemap_url": "https://alpha.example/sitemap.xml",
                "rss_url": "https://alpha.example/feed.xml",
                "api_url": "https://alpha.example/api.json",
            },
        ),
    ]
    opener = FakeOpener(
        """
        <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
          <url><loc>https://alpha.example/reports/a</loc></url>
          <url><loc>https://alpha.example/reports/b</loc></url>
        </urlset>
        """,
        """
        <rss><channel>
          <item><link>https://alpha.example/news/c</link></item>
        </channel></rss>
        """,
        '{"items": [{"url": "https://alpha.example/data/d.json"}]}',
    )

    items = discover_expanded_source_urls(
        sources,
        discovered_at="2026-06-03T00:00:00+00:00",
        opener=opener,
    )

    assert [item.discovery_method for item in items] == [
        "manual_seed",
        "sitemap",
        "sitemap",
        "rss",
        "api",
    ]
    assert [item.url for item in items] == [
        "https://alpha.example/",
        "https://alpha.example/reports/a",
        "https://alpha.example/reports/b",
        "https://alpha.example/news/c",
        "https://alpha.example/data/d.json",
    ]
    assert items[-1].content_type_hint == "application/json"
