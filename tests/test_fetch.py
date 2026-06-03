from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError

from crawler.fetch import (
    checksum_bytes,
    fetch_item,
    fetch_items,
    fetch_log_entry,
)
from crawler.models import AccessDecision, DiscoveredItem, FetchedDocument
from crawler.robots import FetchPolicy


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        url: str = "https://example.org/report",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body
        self.url = url
        self.status = status
        self.headers = headers or {}
        self.closed = False

    def read(self) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        self.closed = True


class FakeOpener:
    def __init__(self, *results) -> None:
        self.results = list(results)
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def item(
    url: str = "https://example.org/report",
    source_id: str = "example-source",
) -> DiscoveredItem:
    return DiscoveredItem(
        item_id=f"item-{source_id}",
        source_id=source_id,
        url=url,
        discovery_method="manual_seed",
        discovered_at="2026-06-03T00:00:00+00:00",
    )


def decision(
    discovered_item: DiscoveredItem,
    *,
    allowed: bool = True,
    reason: str = "allowed",
    rate_limit_seconds: float | None = 0,
) -> AccessDecision:
    return AccessDecision(
        item_id=discovered_item.item_id,
        source_id=discovered_item.source_id,
        url=discovered_item.url,
        allowed=allowed,
        reason=reason,
        checked_at="2026-06-03T00:00:01+00:00",
        user_agent="test-agent/1.0",
        rate_limit_seconds=rate_limit_seconds,
    )


def request_headers(fake_opener: FakeOpener) -> dict[str, str]:
    return dict(fake_opener.requests[0].header_items())


def test_fetch_item_writes_html_cache_and_records_metadata() -> None:
    discovered_item = item("https://example.org/report")
    fake_opener = FakeOpener(
        FakeResponse(
            b"<html><body>ok</body></html>",
            url="https://example.org/final-report",
            headers={
                "Content-Type": "text/html; charset=utf-8",
                "ETag": '"v1"',
                "Last-Modified": "Wed, 03 Jun 2026 00:00:00 GMT",
            },
        ),
    )
    policy = FetchPolicy(user_agent="test-agent/1.0", timeout_seconds=5)

    with TemporaryDirectory() as tmp_dir:
        document = fetch_item(
            discovered_item,
            decision(discovered_item),
            cache_dir=tmp_dir,
            policy=policy,
            opener=fake_opener,
            retrieved_at="2026-06-03T00:00:02+00:00",
        )

        assert document.status_code == 200
        assert document.final_url == "https://example.org/final-report"
        assert document.content_type == "text/html; charset=utf-8"
        assert document.checksum == checksum_bytes(b"<html><body>ok</body></html>")
        assert document.raw_cache_path is not None
        assert Path(document.raw_cache_path).suffix == ".html"
        assert Path(document.raw_cache_path).read_bytes() == b"<html><body>ok</body></html>"
        assert document.metadata["etag"] == '"v1"'
        assert request_headers(fake_opener)["User-agent"] == "test-agent/1.0"
        assert fake_opener.timeouts == [5]


def test_fetch_item_writes_pdf_binary_cache() -> None:
    discovered_item = item("https://example.org/report.pdf")
    fake_opener = FakeOpener(
        FakeResponse(
            b"%PDF-1.4 fixture",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    with TemporaryDirectory() as tmp_dir:
        document = fetch_item(
            discovered_item,
            decision(discovered_item),
            cache_dir=tmp_dir,
            opener=fake_opener,
            retrieved_at="2026-06-03T00:00:02+00:00",
        )

        assert document.fetch_error is None
        assert document.raw_cache_path is not None
        assert Path(document.raw_cache_path).suffix == ".pdf"
        assert Path(document.raw_cache_path).read_bytes() == b"%PDF-1.4 fixture"


def test_fetch_item_skips_disallowed_access_without_opening_url() -> None:
    discovered_item = item()
    fake_opener = FakeOpener()

    with TemporaryDirectory() as tmp_dir:
        document = fetch_item(
            discovered_item,
            decision(discovered_item, allowed=False, reason="disallowed_by_robots_txt"),
            cache_dir=tmp_dir,
            opener=fake_opener,
            retrieved_at="2026-06-03T00:00:02+00:00",
        )

        assert document.status_code is None
        assert document.raw_cache_path is None
        assert document.fetch_error == "skipped_access:disallowed_by_robots_txt"
        assert fake_opener.requests == []


def test_fetch_item_reuses_previous_document_on_http_304() -> None:
    discovered_item = item()
    previous = FetchedDocument(
        document_id="doc-previous",
        source_id=discovered_item.source_id,
        url=discovered_item.url,
        final_url=discovered_item.url,
        status_code=200,
        content_type="text/html",
        retrieved_at="2026-06-02T00:00:00+00:00",
        checksum="sha256:previous",
        raw_cache_path="outputs/runs/previous/raw_cache/doc-previous.html",
        metadata={
            "etag": '"v1"',
            "last_modified": "Wed, 03 Jun 2026 00:00:00 GMT",
        },
    )
    fake_opener = FakeOpener(
        HTTPError(
            discovered_item.url,
            304,
            "Not Modified",
            {"ETag": '"v1"'},
            None,
        ),
    )

    with TemporaryDirectory() as tmp_dir:
        document = fetch_item(
            discovered_item,
            decision(discovered_item),
            cache_dir=tmp_dir,
            opener=fake_opener,
            previous_document=previous,
            retrieved_at="2026-06-03T00:00:02+00:00",
        )

        assert document.status_code == 304
        assert document.checksum == previous.checksum
        assert document.raw_cache_path == previous.raw_cache_path
        assert document.metadata["not_modified"] is True
        headers = request_headers(fake_opener)
        assert headers["If-none-match"] == '"v1"'
        assert headers["If-modified-since"] == "Wed, 03 Jun 2026 00:00:00 GMT"


def test_fetch_item_reuses_previous_cache_when_checksum_matches() -> None:
    discovered_item = item()
    body = b"same content"

    with TemporaryDirectory() as tmp_dir:
        previous_path = Path(tmp_dir) / "previous.html"
        previous_path.write_bytes(body)
        previous = FetchedDocument(
            document_id="doc-previous",
            source_id=discovered_item.source_id,
            url=discovered_item.url,
            checksum=checksum_bytes(body),
            raw_cache_path=str(previous_path),
        )
        document = fetch_item(
            discovered_item,
            decision(discovered_item),
            cache_dir=tmp_dir,
            opener=FakeOpener(
                FakeResponse(body, headers={"Content-Type": "text/html"}),
            ),
            previous_document=previous,
            retrieved_at="2026-06-03T00:00:02+00:00",
        )

        assert document.raw_cache_path == str(previous_path)
        assert document.metadata["not_modified_reason"] == "checksum_match"


def test_fetch_items_continues_after_failure_and_logs_entries() -> None:
    first = item("https://example.org/ok", source_id="alpha")
    second = item("https://example.org/fail", source_id="beta")
    fake_opener = FakeOpener(
        FakeResponse(b"ok", headers={"Content-Type": "text/plain"}),
        URLError("connection refused"),
    )

    with TemporaryDirectory() as tmp_dir:
        documents = fetch_items(
            [
                (first, decision(first)),
                (second, decision(second)),
            ],
            cache_dir=tmp_dir,
            opener=fake_opener,
        )

        assert len(documents) == 2
        assert documents[0].fetch_error is None
        assert documents[1].fetch_error == "url_error:connection refused"
        assert fetch_log_entry(documents[1])["fetch_error"] == "url_error:connection refused"
