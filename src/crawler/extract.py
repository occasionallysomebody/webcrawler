"""Document extraction for fetched public content.

The extraction stage turns fetched bytes into readable text records while
preserving source metadata. Keeping this as its own module makes it clear whether
a run failed because content could not be downloaded or because downloaded
content could not be parsed cleanly.
"""

from __future__ import annotations

from collections.abc import Iterable
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any

from crawler.models import ExtractedDocument, FetchedDocument


HTML_METHOD = "html_trafilatura"
HTML_FALLBACK_METHOD = "html_basic"
PLAIN_TEXT_METHOD = "plain_text"
PDF_METHOD = "pdf_pymupdf"
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
        return extract_pdf_document(document, raw_path.read_bytes())

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
    """Extract readable text and basic metadata from an HTML document.

    The production path uses Trafilatura because public reports often contain
    navigation, legal footers, and related-link chrome that a small HTML parser
    cannot reliably distinguish from article text. The older parser remains as a
    deterministic fallback so malformed pages still produce explicit records.

    Args:
        document (FetchedDocument): Fetched HTML document with provenance.
        raw_bytes (bytes): Cached response body.

    Returns:
        ExtractedDocument: Common extraction record consumed by cleaning,
        redaction, and signal extraction.
    """
    html = _decode(raw_bytes, document.content_type)
    trafilatura_result = _extract_html_with_trafilatura(html, document)
    if trafilatura_result is not None:
        return trafilatura_result

    parser = _parse_html_basic(html)
    text = _normalize_paragraphs(parser.paragraphs)
    quality = extraction_quality(text)
    error = None if text else "empty_extraction"

    return _extracted(
        document,
        title=parser.title,
        published_at=parser.published_at,
        extracted_text=text,
        extraction_method=HTML_FALLBACK_METHOD,
        extraction_quality=quality,
        page_count=1,
        error=error,
        metadata={
            "content_type": document.content_type,
            "final_url": document.final_url,
            "checksum": document.checksum,
            "raw_cache_path": document.raw_cache_path,
            "extractor": "readable_html_parser",
        },
    )


def extract_pdf_document(
    document: FetchedDocument,
    raw_bytes: bytes,
) -> ExtractedDocument:
    """Extract page text and metadata from a PDF document with PyMuPDF.

    Args:
        document (FetchedDocument): Fetched PDF document with provenance.
        raw_bytes (bytes): Cached PDF bytes.

    Returns:
        ExtractedDocument: Common extraction record. Failed PDFs return a
        record with ``extraction_quality='failed'`` instead of raising, so a
        crawl can continue after one broken report.
    """

    try:
        import fitz
    except ImportError:
        return _extracted(
            document,
            extraction_method="pdf_unavailable",
            extraction_quality="failed",
            error="pymupdf_not_installed",
        )

    try:
        pdf = fitz.open(stream=raw_bytes, filetype="pdf")
    except Exception as error:
        return _extracted(
            document,
            extraction_method=PDF_METHOD,
            extraction_quality="failed",
            error=f"pdf_open_failed:{type(error).__name__}",
            metadata=_base_metadata(document, extractor="pymupdf"),
        )

    try:
        page_texts = []
        page_summaries = []
        for index, page in enumerate(pdf, start=1):
            page_text = _normalize_text(page.get_text("text"))
            if page_text:
                page_texts.append(f"[Page {index}]\n{page_text}")
            page_summaries.append(
                {
                    "page_number": index,
                    "text_length": len(page_text),
                    "word_count": len(re.findall(r"\b\w+\b", page_text)),
                }
            )
        text = _normalize_paragraphs(page_texts)
        metadata = dict(pdf.metadata or {})
        title = _normalize_inline(str(metadata.get("title") or "")) or None
        published_at = _pdf_date(metadata.get("creationDate") or metadata.get("modDate"))
        return _extracted(
            document,
            title=title,
            published_at=published_at,
            extracted_text=text,
            extraction_method=PDF_METHOD,
            extraction_quality=extraction_quality(text),
            page_count=pdf.page_count,
            error=None if text else "empty_extraction",
            metadata={
                **_base_metadata(document, extractor="pymupdf"),
                "pdf_metadata": {key: value for key, value in metadata.items() if value},
                "pages": page_summaries,
            },
        )
    finally:
        pdf.close()


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
            **_base_metadata(document, extractor="plain_text"),
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


def _extract_html_with_trafilatura(
    html: str,
    document: FetchedDocument,
) -> ExtractedDocument | None:
    """Extract HTML with Trafilatura when the dependency can parse the page.

    Args:
        html (str): Decoded HTML content.
        document (FetchedDocument): Fetched document provenance.

    Returns:
        ExtractedDocument | None: Extraction record when Trafilatura returns
        useful content, otherwise ``None`` so the caller can use the basic
        fallback parser.
    """

    try:
        import trafilatura
    except ImportError:
        return None

    try:
        extracted = trafilatura.extract(
            html,
            url=document.final_url or document.url,
            include_comments=False,
            include_tables=True,
            output_format="txt",
            favor_recall=True,
        )
        metadata = trafilatura.extract_metadata(html, default_url=document.final_url or document.url)
    except Exception:
        return None

    text = _normalize_text(extracted or "")
    if not text:
        return None
    if extraction_quality(text) == "low":
        fallback = _parse_html_basic(html)
        if not _normalize_paragraphs(fallback.paragraphs):
            return None

    title = None
    published_at = None
    if metadata is not None:
        title = _normalize_inline(str(getattr(metadata, "title", "") or "")) or None
        published_at = _normalize_inline(str(getattr(metadata, "date", "") or "")) or None

    return _extracted(
        document,
        title=title,
        published_at=published_at,
        extracted_text=text,
        extraction_method=HTML_METHOD,
        extraction_quality=extraction_quality(text),
        page_count=1,
        error=None,
        metadata={
            **_base_metadata(document, extractor="trafilatura"),
        },
    )


def _parse_html_basic(html: str) -> ReadableHTMLParser:
    """Parse HTML with the built-in fallback parser.

    Args:
        html (str): Decoded HTML content.

    Returns:
        ReadableHTMLParser: Parser containing collected title, date, and
        paragraph values.
    """

    parser = ReadableHTMLParser()
    parser.feed(html)
    parser.close()
    return parser


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
        """Initialize the object and keep its stored state explicit.
        
        This private helper keeps the public function small and testable. It is
        documented because new maintainers often need to inspect these helpers when
        debugging a crawl run.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
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
        """Handle an opening HTML tag while extracting readable text.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Args:
            tag (str): HTML tag name currently being handled by the parser.
            attrs (list[tuple[str, str | None]]): HTML tag attributes captured by the
                parser.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
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
        """Handle a closing HTML tag while extracting readable text.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Args:
            tag (str): HTML tag name currently being handled by the parser.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
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
        """Collect visible text from the current HTML parser position.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Args:
            data (str): Raw parser data or map data used by the current helper.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
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
        """Finish parser processing and flush any pending text.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
        self._flush()
        super().close()

    def _flush(self) -> None:
        """Support the module's public workflow by computing flush.
        
        This private helper keeps the public function small and testable. It is
        documented because new maintainers often need to inspect these helpers when
        debugging a crawl run.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
        text = _normalize_inline(" ".join(self._current))
        self._current = []
        if text:
            self.paragraphs.append(text)

    def _read_meta(self, attrs: dict[str, str]) -> None:
        """Support the module's public workflow by computing read meta.
        
        This private helper keeps the public function small and testable. It is
        documented because new maintainers often need to inspect these helpers when
        debugging a crawl run.
        
        Args:
            attrs (dict[str, str]): HTML tag attributes captured by the parser.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
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
    """Support the module's public workflow by computing extracted.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        document (FetchedDocument): Document record being transformed by this helper.
        title (str | None): Value named ``title`` supplied by the caller for this
            pipeline step.
        published_at (str | None): Value named ``published_at`` supplied by the caller
            for this pipeline step.
        extracted_text (str): Value named ``extracted_text`` supplied by the caller for
            this pipeline step.
        extraction_method (str): Value named ``extraction_method`` supplied by the
            caller for this pipeline step.
        extraction_quality (str): Value named ``extraction_quality`` supplied by the
            caller for this pipeline step.
        page_count (int | None): Value named ``page_count`` supplied by the caller for
            this pipeline step.
        error (str | None): Value named ``error`` supplied by the caller for this
            pipeline step.
        metadata (dict[str, Any] | None): Value named ``metadata`` supplied by the
            caller for this pipeline step.
    
    Returns:
        ExtractedDocument: Result produced for the next pipeline step or caller.
    """
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
    """Support the module's public workflow by computing content type.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        document (FetchedDocument): Document record being transformed by this helper.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    return (document.content_type or "").split(";", 1)[0].strip().lower()


def _decode(raw_bytes: bytes, content_type: str | None) -> str:
    """Support the module's public workflow by computing decode.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        raw_bytes (bytes): Raw response bytes fetched from the public source.
        content_type (str | None): HTTP content type used to choose an extraction or
            cache strategy.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
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


def _base_metadata(document: FetchedDocument, *, extractor: str) -> dict[str, Any]:
    """Return common extraction metadata preserved across extractor types.

    Args:
        document (FetchedDocument): Fetched document record.
        extractor (str): Concrete extractor implementation name.

    Returns:
        dict[str, Any]: Metadata that links extracted text back to fetch
        provenance.
    """

    return {
        "content_type": document.content_type,
        "final_url": document.final_url,
        "checksum": document.checksum,
        "raw_cache_path": document.raw_cache_path,
        "retrieved_at": document.retrieved_at,
        "extractor": extractor,
    }


def _pdf_date(value: Any) -> str | None:
    """Normalize a PDF metadata date when PyMuPDF supplies one.

    Args:
        value (Any): Raw PDF date metadata, often in ``D:YYYYMMDDHHmmSS`` form.

    Returns:
        str | None: ISO-like date string when a year/month/day is available.
    """

    text = str(value or "").strip()
    match = re.search(r"D:(\d{4})(\d{2})(\d{2})", text)
    if match:
        return "-".join(match.groups())
    return text or None


def _normalize_text(text: str) -> str:
    """Support the module's public workflow by computing normalize text.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        text (str): Text content being parsed, cleaned, redacted, or searched.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    paragraphs = [line for line in text.splitlines()]
    return _normalize_paragraphs(paragraphs)


def _normalize_paragraphs(paragraphs: list[str]) -> str:
    """Support the module's public workflow by computing normalize paragraphs.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        paragraphs (list[str]): Paragraph strings that have already been split from a
            larger document.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    cleaned = [_normalize_inline(paragraph) for paragraph in paragraphs]
    return "\n\n".join(paragraph for paragraph in cleaned if paragraph)


def _normalize_inline(text: str) -> str:
    """Support the module's public workflow by computing normalize inline.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        text (str): Text content being parsed, cleaned, redacted, or searched.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    return re.sub(r"\s+", " ", text).strip()
