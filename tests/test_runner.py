import json
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.error import HTTPError

from crawler.runner import main, run_pipeline
from crawler.storage import fetch_run_summary, initialize_sqlite, read_jsonl


FIXTURES = Path(__file__).parent / "fixtures"


class FakeResponse:
    def __init__(
        self,
        body: bytes | str,
        *,
        url: str = "https://alpha.example/report",
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.body = body.encode("utf-8") if isinstance(body, str) else body
        self.url = url
        self.status = status
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}

    def read(self) -> bytes:
        return self.body

    def getcode(self) -> int:
        return self.status

    def geturl(self) -> str:
        return self.url

    def close(self) -> None:
        return None


class FakeOpener:
    def __init__(self, *responses: FakeResponse) -> None:
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_run_pipeline_writes_summary_logs_and_records() -> None:
    with TemporaryDirectory() as tmp_dir:
        result = run_pipeline(
            source_registry_path=FIXTURES / "sources_valid.csv",
            output_root=tmp_dir,
            run_id="test-run",
        )
        summary_path = result.output_dir / "run_summary.json"
        logs_path = result.output_dir / "logs" / "run_events.jsonl"
        records_path = result.output_dir / "records" / "discovered_items.jsonl"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        records = read_jsonl(records_path)

    assert summary["status"] == "success"
    assert summary["sources_loaded"] == 1
    assert summary["items_discovered"] == 1
    assert logs_path.name == "run_events.jsonl"
    assert records[0]["source_id"] == "alpha"


def test_run_pipeline_respects_source_and_item_limits() -> None:
    with TemporaryDirectory() as tmp_dir:
        result = run_pipeline(
            source_registry_path=FIXTURES / "sources_valid.csv",
            output_root=tmp_dir,
            run_id="limited-run",
            max_sources=1,
            max_items_per_source=0,
        )

    assert result.summary["sources_loaded"] == 1
    assert result.summary["items_discovered"] == 0


def test_runner_main_returns_success() -> None:
    with TemporaryDirectory() as tmp_dir:
        exit_code = main(
            [
                "--source-registry",
                str(FIXTURES / "sources_valid.csv"),
                "--output-root",
                tmp_dir,
                "--run-id",
                "cli-run",
            ],
        )

    assert exit_code == 0


def test_runner_can_mirror_run_to_sqlite_storage() -> None:
    with TemporaryDirectory() as tmp_dir:
        db_path = Path(tmp_dir) / "storage" / "crawler.sqlite"
        result = run_pipeline(
            source_registry_path=FIXTURES / "sources_valid.csv",
            output_root=Path(tmp_dir) / "runs",
            run_id="sqlite-run",
            storage_backend="sqlite",
            run_db_path=db_path,
        )
        connection = initialize_sqlite(db_path)
        summary = fetch_run_summary(connection, "sqlite-run")
        connection.close()

    assert result.summary["status"] == "success"
    assert result.summary["durable_storage"]["record_count"] >= 1
    assert summary["run_id"] == "sqlite-run"


def test_run_pipeline_can_build_map_ui() -> None:
    with TemporaryDirectory() as tmp_dir:
        result = run_pipeline(
            source_registry_path=FIXTURES / "sources_valid.csv",
            output_root=tmp_dir,
            run_id="ui-run",
            enabled_stages=["validate_sources", "discover_items", "build_map_ui"],
        )
        ui_path = result.output_dir / "ui" / "azerbaijan_energy_map.html"
        content = ui_path.read_text(encoding="utf-8")

    assert result.summary["status"] == "success"
    assert "Azerbaijan Energy Intelligence" in content
    assert "maplibre-gl" in content


def test_run_pipeline_automatic_crawl_feeds_live_map_records() -> None:
    csv_content = "\n".join(
        [
            "source_id,name,tier,publisher_type,base_url,access_method,"
            "rate_limit_seconds,robots_required,enabled,notes,sitemap_url,rss_url,"
            "api_url,allowed_paths,blocked_paths,language,country,domain_tags,"
            "known_bias_or_limitation",
            "alpha,Alpha Source,tier_1,multilateral,https://alpha.example/report,"
            "public_html,0,false,true,gas flaring source,,,,,,en,Azerbaijan,"
            "gas_flaring|ecology,fixture only",
        ]
    )
    body = (
        b"<html><head><title>Alpha</title></head><body><main>"
        b"<p>Global Witness reported gas flaring pollution in Azerbaijan near "
        b"Sangachal terminal in 2025.</p>"
        b"</main></body></html>"
    )

    with TemporaryDirectory() as tmp_dir:
        registry_path = Path(tmp_dir) / "sources.csv"
        registry_path.write_text(csv_content, encoding="utf-8")
        result = run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="crawl-run",
            enabled_stages=["automatic_crawl"],
            max_fetches=1,
            opener=FakeOpener(FakeResponse(body)),
        )
        records_dir = result.output_dir / "records"
        claims = read_jsonl(records_dir / "claims.jsonl")
        trust_scores = read_jsonl(records_dir / "trust_scores.jsonl")
        source_health = read_jsonl(records_dir / "source_health.jsonl")
        retry_candidates = read_jsonl(records_dir / "retry_candidates.jsonl")
        ui_path = result.output_dir / "ui" / "azerbaijan_energy_map.html"
        content = ui_path.read_text(encoding="utf-8")
        payload = content.split('<script type="application/json" id="map-data">')[1]
        map_data = json.loads(payload.split("</script>", 1)[0])

    assert result.summary["status"] == "success"
    assert result.summary["documents_fetched"] == 1
    assert result.summary["claims_extracted"] == 1
    assert len(claims) == 1
    assert len(trust_scores) == 1
    assert len(source_health) == 1
    assert retry_candidates == []
    assert result.summary["source_health_records"] == 1
    assert map_data["summary"]["claims"] == 1
    assert any(
        feature["properties"]["layer"] == "claim"
        for feature in map_data["features"]["features"]
    )


def test_run_pipeline_expands_approved_sitemap_discovery() -> None:
    sitemap = """
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <url><loc>https://alpha.example/reports/one</loc></url>
      <url><loc>https://alpha.example/reports/two</loc></url>
    </urlset>
    """

    with TemporaryDirectory() as tmp_dir:
        result = run_pipeline(
            source_registry_path=FIXTURES / "sources_valid.csv",
            output_root=tmp_dir,
            run_id="expanded-run",
            enabled_stages=["expand_discovery"],
            max_items_per_source=3,
            opener=FakeOpener(FakeResponse(sitemap)),
        )
        records = read_jsonl(result.output_dir / "records" / "discovered_items.jsonl")

    assert result.summary["status"] == "success"
    assert result.summary["items_discovered"] == 3
    assert [record["discovery_method"] for record in records] == [
        "manual_seed",
        "sitemap",
        "sitemap",
    ]


def test_scheduled_crawl_skips_unchanged_documents_downstream() -> None:
    csv_content = _single_source_csv()
    body = (
        b"<html><head><title>Alpha</title></head><body><main>"
        b"<p>Global Witness reported gas flaring pollution in Azerbaijan near "
        b"Sangachal terminal in 2025.</p>"
        b"</main></body></html>"
    )

    with TemporaryDirectory() as tmp_dir:
        registry_path = Path(tmp_dir) / "sources.csv"
        registry_path.write_text(csv_content, encoding="utf-8")
        first = run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="first-run",
            enabled_stages=["automatic_crawl"],
            max_fetches=1,
            opener=FakeOpener(
                FakeResponse(body, headers={"Content-Type": "text/html", "ETag": "v1"})
            ),
        )
        opener = FakeOpener(
            FakeResponse(body, headers={"Content-Type": "text/html", "ETag": "v1"})
        )
        second = run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="second-run",
            enabled_stages=["scheduled_crawl"],
            max_fetches=1,
            opener=opener,
            previous_run_id="first-run",
        )
        incremental = read_jsonl(second.output_dir / "records" / "incremental_fetches.jsonl")
        extracted = read_jsonl(second.output_dir / "records" / "extracted_documents.jsonl")
        claims = read_jsonl(second.output_dir / "records" / "claims.jsonl")

    assert first.summary["claims_extracted"] == 1
    assert second.summary["previous_run_id"] == "first-run"
    assert second.summary["incremental_summary"]["unchanged"] == 1
    assert incremental[0]["status"] == "unchanged"
    assert extracted == []
    assert claims == []
    assert opener.requests[0].headers["If-none-match"] == "v1"


def test_scheduled_crawl_processes_changed_documents() -> None:
    csv_content = _single_source_csv()
    first_body = (
        b"<html><body><main><p>Global Witness reported gas flaring pollution "
        b"in Azerbaijan in 2025.</p></main></body></html>"
    )
    changed_body = (
        b"<html><body><main><p>Global Witness reported gas flaring pollution "
        b"in Azerbaijan in 2026 with updated evidence near Sangachal terminal.</p>"
        b"</main></body></html>"
    )

    with TemporaryDirectory() as tmp_dir:
        registry_path = Path(tmp_dir) / "sources.csv"
        registry_path.write_text(csv_content, encoding="utf-8")
        run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="first-run",
            enabled_stages=["automatic_crawl"],
            max_fetches=1,
            opener=FakeOpener(FakeResponse(first_body)),
        )
        second = run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="second-run",
            enabled_stages=["incremental_crawl"],
            max_fetches=1,
            opener=FakeOpener(FakeResponse(changed_body)),
            previous_run_id="first-run",
        )
        incremental = read_jsonl(second.output_dir / "records" / "incremental_fetches.jsonl")
        extracted = read_jsonl(second.output_dir / "records" / "extracted_documents.jsonl")

    assert second.summary["incremental_summary"]["changed"] == 1
    assert incremental[0]["status"] == "changed"
    assert incremental[0]["previous_document_id"] == incremental[0]["document_id"]
    assert len(extracted) == 1
    assert "2026 with updated evidence" in extracted[0]["extracted_text"]


def test_scheduled_crawl_records_not_modified_responses() -> None:
    csv_content = _single_source_csv()
    body = (
        b"<html><body><main><p>Global Witness reported gas flaring pollution "
        b"in Azerbaijan in 2025.</p></main></body></html>"
    )

    with TemporaryDirectory() as tmp_dir:
        registry_path = Path(tmp_dir) / "sources.csv"
        registry_path.write_text(csv_content, encoding="utf-8")
        run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="first-run",
            enabled_stages=["automatic_crawl"],
            max_fetches=1,
            opener=FakeOpener(
                FakeResponse(body, headers={"Content-Type": "text/html", "ETag": "v1"})
            ),
        )
        not_modified = HTTPError(
            url="https://alpha.example/report",
            code=304,
            msg="Not Modified",
            hdrs={"ETag": "v1"},
            fp=None,
        )
        second = run_pipeline(
            source_registry_path=registry_path,
            output_root=tmp_dir,
            run_id="second-run",
            enabled_stages=["scheduled_crawl"],
            max_fetches=1,
            opener=FakeOpener(not_modified),
            previous_run_id="first-run",
        )
        fetched = read_jsonl(second.output_dir / "records" / "fetched_documents.jsonl")
        incremental = read_jsonl(second.output_dir / "records" / "incremental_fetches.jsonl")

    assert fetched[0]["status_code"] == 304
    assert incremental[0]["status"] == "unchanged"
    assert second.summary["documents_extracted"] == 0


def _single_source_csv() -> str:
    return "\n".join(
        [
            "source_id,name,tier,publisher_type,base_url,access_method,"
            "rate_limit_seconds,robots_required,enabled,notes,sitemap_url,rss_url,"
            "api_url,allowed_paths,blocked_paths,language,country,domain_tags,"
            "known_bias_or_limitation",
            "alpha,Alpha Source,tier_1,multilateral,https://alpha.example/report,"
            "public_html,0,false,true,gas flaring source,,,,,,en,Azerbaijan,"
            "gas_flaring|ecology,fixture only",
        ]
    )
