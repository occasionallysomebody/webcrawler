"""Text extraction from fetched raw-cache documents."""

from __future__ import annotations

from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from crawler.models import ExtractedDocument, FetchedDocument


HTML_METHOD = "html"
PLAIN_TEXT_METHOD = "plain_text"
PDF_METHOD = "pdf_unsupported"
UNSUPPORTED_METHOD = "unsupported"


def extract_document(document: FetchedDocument) -> ExtractedDocument:
    """Convert one fetched document into the common extracted shape."""
    if document.fetch_error:
        return _extracted(
            document,
            extraction_method="not_attempted",
            extraction_quality="failed",
            error=f"fetch_error:{document.fetch_error}",
        )

    if not document.raw_cache_path:
        return _extracted(
            document,
            extraction_method="not_attempted",
            extraction_quality="failed",
            error="missing_raw_cache_path",
        )

    raw_path = Path(document.raw_cache_path)
    if not raw_path.exists():
        return _extracted(
            document,
            extraction_method="not_attempted",
            extraction_quality="failed",
            error=f"raw_cache_path_not_found:{raw_path}",
        )

    content_type = _content_type(document)
    if content_type == "application/pdf" or raw_path.suffix.lower() == ".pdf":
        return _extracted(
            document,
            extraction_method=PDF_METHOD,
            extraction_quality="failed",
            error="pdf_extraction_not_configured",
        )

    raw_bytes = raw_path.read_bytes()
    if content_type.startswith("text/html") or raw_path.suffix.lower() in {
        ".html",
        ".htm",
    }:
        return extract_html_document(document, raw_bytes)

    if content_type.startswith("text/plain") or raw_path.suffix.lower() in {
        ".txt",
        ".text",
    }:
        return extract_plain_text_document(document, raw_bytes)

    return _extracted(
        document,
        extraction_method=UNSUPPORTED_METHOD,
        extraction_quality="failed",
        error=f"unsupported_content_type:{content_type or 'unknown'}",
    )


def extract_documents(
    documents: Iterable[FetchedDocument],
) -> list[ExtractedDocument]:
    """Extract many fetched documents, preserving item-level failures."""
    return [extract_document(document) for document in documents]


def extract_html_document(
    document: FetchedDocument,
    raw_bytes: bytes,
) -> ExtractedDocument:
    """Extract readable text and basic metadata from an HTML document."""
    html = _decode(raw_bytes, document.content_type)
    parser = ReadableHTMLParser()
    parser.feed(html)
    parser.close()

    text = _normalize_paragraphs(parser.paragraphs)
    quality = extraction_quality(text)
    error = None if text else "empty_extraction"

    return _extracted(
        document,
        title=parser.title,
        published_at=parser.published_at,
        extracted_text=text,
        extraction_method=HTML_METHOD,
        extraction_quality=quality,
        page_count=1,
        error=error,
        metadata={
            "content_type": document.content_type,
            "final_url": document.final_url,
            "checksum": document.checksum,
            "raw_cache_path": document.raw_cache_path,
        },
    )


def extract_plain_text_document(
    document: FetchedDocument,
    raw_bytes: bytes,
) -> ExtractedDocument:
    """Extract normalized text from a plain-text document."""
    text = _normalize_text(_decode(raw_bytes, document.content_type))
    return _extracted(
        document,
        extracted_text=text,
        extraction_method=PLAIN_TEXT_METHOD,
        extraction_quality=extraction_quality(text),
        page_count=1,
        error=None if text else "empty_extraction",
        metadata={
            "content_type": document.content_type,
            "final_url": document.final_url,
            "checksum": document.checksum,
            "raw_cache_path": document.raw_cache_path,
        },
    )


def extraction_quality(text: str) -> str:
    """Return a coarse deterministic quality flag for extracted text."""
    word_count = len(re.findall(r"\b\w+\b", text))
    if word_count == 0:
        return "empty"
    if word_count < 20:
        return "low"
    if word_count < 100:
        return "medium"
    return "high"


def extraction_log_entry(document: ExtractedDocument) -> dict[str, object]:
    """Create a structured log entry for extraction output."""
    return {
        "stage": "extract_text",
        "document_id": document.document_id,
        "source_id": document.source_id,
        "url": document.url,
        "extraction_method": document.extraction_method,
        "extraction_quality": document.extraction_quality,
        "text_length": len(document.extracted_text),
        "error": document.error,
    }


class ReadableHTMLParser(HTMLParser):
    """Small HTML text extractor with title and publication-date hints."""

    BLOCK_TAGS = {
        "article",
        "blockquote",
        "br",
        "dd",
        "div",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "li",
        "main",
        "p",
        "section",
        "td",
        "th",
        "tr",
    }
    SKIP_TAGS = {"script", "style", "noscript", "svg"}
    CHROME_TAGS = {"footer", "header", "nav"}
    DATE_META_NAMES = {
        "article:published_time",
        "date",
        "dc.date",
        "dc.date.issued",
        "pubdate",
        "publishdate",
        "published_time",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title: str | None = None
        self.published_at: str | None = None
        self.paragraphs: list[str] = []
        self._current: list[str] = []
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        lowered = tag.lower()
        attrs_dict = {key.lower(): value for key, value in attrs if value is not None}

        if lowered in self.SKIP_TAGS or lowered in self.CHROME_TAGS:
            self._skip_depth += 1
            return

        if lowered == "title":
            self._in_title = True
            return

        if lowered == "meta":
            self._read_meta(attrs_dict)
            return

        if lowered in self.BLOCK_TAGS:
            self._flush()

    def handle_endtag(self, tag: str) -> None:
        lowered = tag.lower()
        if self._skip_depth:
            if lowered in self.SKIP_TAGS or lowered in self.CHROME_TAGS:
                self._skip_depth -= 1
            return

        if lowered == "title":
            self._in_title = False
            return

        if lowered in self.BLOCK_TAGS:
            self._flush()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        cleaned = _normalize_inline(data)
        if not cleaned:
            return
        if self._in_title:
            title = _normalize_inline(cleaned)
            if title:
                self.title = title
            return
        self._current.append(cleaned)

    def close(self) -> None:
        self._flush()
        super().close()

    def _flush(self) -> None:
        text = _normalize_inline(" ".join(self._current))
        self._current = []
        if text:
            self.paragraphs.append(text)

    def _read_meta(self, attrs: dict[str, str]) -> None:
        content = attrs.get("content", "").strip()
        if not content:
            return

        property_name = attrs.get("property", "").lower()
        name = attrs.get("name", "").lower()
        if property_name == "og:title":
            self.title = content
        if (
            property_name in self.DATE_META_NAMES or name in self.DATE_META_NAMES
        ) and not self.published_at:
            self.published_at = content


def _extracted(
    document: FetchedDocument,
    *,
    title: str | None = None,
    published_at: str | None = None,
    extracted_text: str = "",
    extraction_method: str,
    extraction_quality: str,
    page_count: int | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ExtractedDocument:
    return ExtractedDocument(
        document_id=document.document_id,
        source_id=document.source_id,
        url=document.url,
        title=title,
        published_at=published_at,
        extracted_text=extracted_text,
        extraction_method=extraction_method,
        extraction_quality=extraction_quality,
        page_count=page_count,
        error=error,
        metadata=dict(metadata or {}),
    )


def _content_type(document: FetchedDocument) -> str:
    return (document.content_type or "").split(";", 1)[0].strip().lower()


def _decode(raw_bytes: bytes, content_type: str | None) -> str:
    charset_match = re.search(
        r"charset=([\w.-]+)",
        content_type or "",
        flags=re.IGNORECASE,
    )
    encoding = charset_match.group(1) if charset_match else "utf-8"
    try:
        return raw_bytes.decode(encoding)
    except (LookupError, UnicodeDecodeError):
        return raw_bytes.decode("utf-8", errors="replace")


def _normalize_text(text: str) -> str:
    paragraphs = [line for line in text.splitlines()]
    return _normalize_paragraphs(paragraphs)


def _normalize_paragraphs(paragraphs: list[str]) -> str:
    cleaned = [_normalize_inline(paragraph) for paragraph in paragraphs]
    return "\n\n".join(paragraph for paragraph in cleaned if paragraph)


def _normalize_inline(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
