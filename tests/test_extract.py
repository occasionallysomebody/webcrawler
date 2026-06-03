from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.extract import (
    extract_document,
    extract_documents,
    extraction_log_entry,
    extraction_quality,
)
from crawler.models import FetchedDocument


def fetched_document(
    raw_cache_path: str | None,
    *,
    content_type: str | None = "text/html; charset=utf-8",
    fetch_error: str | None = None,
) -> FetchedDocument:
    return FetchedDocument(
        document_id="doc-001",
        source_id="example-source",
        url="https://example.org/report",
        final_url="https://example.org/final-report",
        status_code=200,
        content_type=content_type,
        retrieved_at="2026-06-03T00:00:00+00:00",
        checksum="sha256:fixture",
        raw_cache_path=raw_cache_path,
        fetch_error=fetch_error,
    )


def test_extract_document_reads_html_title_date_and_text() -> None:
    html = """<!doctype html>
    <html>
      <head>
        <title>Ignored browser title</title>
        <meta property="og:title" content="Azerbaijan Energy Report">
        <meta property="article:published_time" content="2026-05-30">
      </head>
      <body>
        <header>Navigation should not appear</header>
        <main>
          <h1>Azerbaijan Energy Report</h1>
          <p>First paragraph about public energy-sector evidence.</p>
          <p>Second paragraph with enough context for analyst review.</p>
        </main>
        <script>console.log("skip")</script>
      </body>
    </html>"""

    with TemporaryDirectory() as tmp_dir:
        html_path = Path(tmp_dir) / "doc.html"
        html_path.write_text(html, encoding="utf-8")
        extracted = extract_document(fetched_document(str(html_path)))

    assert extracted.document_id == "doc-001"
    assert extracted.source_id == "example-source"
    assert extracted.url == "https://example.org/report"
    assert extracted.title == "Azerbaijan Energy Report"
    assert extracted.published_at == "2026-05-30"
    assert extracted.extraction_method == "html"
    assert "Navigation should not appear" not in extracted.extracted_text
    assert "First paragraph about public energy-sector evidence." in extracted.extracted_text
    assert extracted.metadata["final_url"] == "https://example.org/final-report"
    assert extracted.page_count == 1
    assert extracted.error is None


def test_extract_document_flags_empty_html_as_low_quality() -> None:
    with TemporaryDirectory() as tmp_dir:
        html_path = Path(tmp_dir) / "empty.html"
        html_path.write_text("<html><body><nav>Only navigation</nav></body></html>", encoding="utf-8")
        extracted = extract_document(fetched_document(str(html_path)))

    assert extracted.extracted_text == ""
    assert extracted.extraction_quality == "empty"
    assert extracted.error == "empty_extraction"


def test_extract_document_reads_plain_text() -> None:
    with TemporaryDirectory() as tmp_dir:
        text_path = Path(tmp_dir) / "report.txt"
        text_path.write_text("Line one.\n\nLine two with context.", encoding="utf-8")
        extracted = extract_document(
            fetched_document(str(text_path), content_type="text/plain"),
        )

    assert extracted.extraction_method == "plain_text"
    assert extracted.extracted_text == "Line one.\n\nLine two with context."


def test_extract_document_returns_failure_records_for_unusable_fetches() -> None:
    missing_cache = extract_document(fetched_document(None))
    fetch_failed = extract_document(
        fetched_document(None, fetch_error="http_error:404"),
    )

    assert missing_cache.extraction_quality == "failed"
    assert missing_cache.error == "missing_raw_cache_path"
    assert fetch_failed.error == "fetch_error:http_error:404"


def test_extract_document_explicitly_marks_pdf_unsupported() -> None:
    with TemporaryDirectory() as tmp_dir:
        pdf_path = Path(tmp_dir) / "report.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fixture")
        extracted = extract_document(
            fetched_document(str(pdf_path), content_type="application/pdf"),
        )

    assert extracted.extraction_method == "pdf_unsupported"
    assert extracted.extraction_quality == "failed"
    assert extracted.error == "pdf_extraction_not_configured"


def test_extract_documents_continues_and_logs_entries() -> None:
    with TemporaryDirectory() as tmp_dir:
        html_path = Path(tmp_dir) / "doc.html"
        html_path.write_text("<html><body><p>Useful paragraph.</p></body></html>", encoding="utf-8")
        extracted = extract_documents(
            [
                fetched_document(str(html_path)),
                fetched_document(None),
            ],
        )

    assert len(extracted) == 2
    assert extracted[0].error is None
    assert extracted[1].error == "missing_raw_cache_path"
    assert extraction_log_entry(extracted[0])["stage"] == "extract_text"


def test_extraction_quality_thresholds() -> None:
    assert extraction_quality("") == "empty"
    assert extraction_quality("short text") == "low"
    assert extraction_quality("word " * 25) == "medium"
    assert extraction_quality("word " * 120) == "high"
