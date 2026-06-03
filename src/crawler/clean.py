"""Deterministic cleaning and normalization for extracted text."""

from __future__ import annotations

from collections.abc import Iterable
import re
from typing import Any

from crawler.models import CleanDocument, ExtractedDocument


CLEANING_METHOD = "normalize_whitespace_v1"

BOILERPLATE_PATTERNS = (
    re.compile(r"^(accept|reject|manage)\s+(all\s+)?cookies\b", re.IGNORECASE),
    re.compile(r"^cookie(s)?\s+(settings|policy|preferences)\b", re.IGNORECASE),
    re.compile(r"^(subscribe|sign up)\s+(to|for)\b", re.IGNORECASE),
    re.compile(r"^(share|follow us|related articles?)\b", re.IGNORECASE),
    re.compile(r"^(skip to|back to top|menu|search)\b", re.IGNORECASE),
    re.compile(r"^(privacy policy|terms of use|all rights reserved)\b", re.IGNORECASE),
)


def clean_document(document: ExtractedDocument) -> CleanDocument:
    """Clean one extracted document without mutating the source record."""
    flags: list[str] = []

    if document.error:
        flags.append("source_extraction_error")
    if not document.extracted_text.strip():
        flags.append("empty_input")
        return _cleaned(document, "", flags)

    paragraphs, removed_count, duplicate_count = normalize_paragraphs(
        document.extracted_text,
    )
    if removed_count:
        flags.append("boilerplate_removed")
    if duplicate_count:
        flags.append("duplicate_paragraphs_removed")

    clean_text = "\n\n".join(paragraphs)
    word_count = count_words(clean_text)
    if word_count == 0:
        flags.append("empty_output")
    elif word_count < 20:
        flags.append("short_text")

    language = detect_language(clean_text)
    if language is None:
        flags.append("language_unknown")

    return _cleaned(
        document,
        clean_text,
        flags,
        word_count=word_count,
        language=language,
        metadata={
            "source_url": document.url,
            "source_title": document.title,
            "source_published_at": document.published_at,
            "extraction_method": document.extraction_method,
            "extraction_quality": document.extraction_quality,
            "removed_boilerplate_paragraphs": removed_count,
            "removed_duplicate_paragraphs": duplicate_count,
        },
    )


def clean_documents(
    documents: Iterable[ExtractedDocument],
) -> list[CleanDocument]:
    """Clean many extracted documents, preserving one output per input."""
    return [clean_document(document) for document in documents]


def normalize_paragraphs(text: str) -> tuple[list[str], int, int]:
    """Normalize paragraphs and return removal counts."""
    paragraphs: list[str] = []
    removed_count = 0
    duplicate_count = 0
    previous_key: str | None = None

    for raw_paragraph in _split_paragraphs(text):
        paragraph = normalize_whitespace(raw_paragraph)
        if not paragraph:
            continue
        if is_boilerplate(paragraph):
            removed_count += 1
            continue

        key = paragraph.casefold()
        if key == previous_key:
            duplicate_count += 1
            continue

        paragraphs.append(paragraph)
        previous_key = key

    return paragraphs, removed_count, duplicate_count


def normalize_whitespace(text: str) -> str:
    """Collapse inline whitespace while preserving paragraph-level callers."""
    cleaned = text.replace("\u00a0", " ")
    cleaned = re.sub(r"[ \t\r\f\v]+", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    return cleaned.strip()


def is_boilerplate(paragraph: str) -> bool:
    """Return true for conservative page-chrome boilerplate lines."""
    normalized = normalize_whitespace(paragraph)
    if not normalized:
        return True
    if len(normalized) > 160:
        return False
    return any(pattern.search(normalized) for pattern in BOILERPLATE_PATTERNS)


def count_words(text: str) -> int:
    """Count readable word-like tokens."""
    return len(re.findall(r"\b[\w'-]+\b", text))


def detect_language(text: str) -> str | None:
    """Return a lightweight language hint when detection is obvious."""
    if not text.strip():
        return None
    ascii_letters = len(re.findall(r"[A-Za-z]", text))
    cyrillic_letters = len(re.findall(r"[\u0400-\u04ff]", text))
    total_letters = ascii_letters + cyrillic_letters
    if total_letters == 0:
        return None
    if cyrillic_letters / total_letters > 0.5:
        return "ru"
    if ascii_letters / total_letters > 0.7:
        return "en"
    return None


def cleaning_log_entry(document: CleanDocument) -> dict[str, object]:
    """Create a structured log entry for cleaning output."""
    return {
        "stage": "clean_text",
        "document_id": document.document_id,
        "word_count": document.word_count,
        "language": document.language,
        "quality_flags": document.quality_flags,
    }


def _cleaned(
    document: ExtractedDocument,
    clean_text: str,
    quality_flags: list[str],
    *,
    word_count: int | None = None,
    language: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> CleanDocument:
    return CleanDocument(
        document_id=document.document_id,
        clean_text=clean_text,
        cleaning_method=CLEANING_METHOD,
        word_count=count_words(clean_text) if word_count is None else word_count,
        language=language,
        quality_flags=quality_flags,
        metadata=dict(metadata or {}),
    )


def _split_paragraphs(text: str) -> list[str]:
    normalized_newlines = text.replace("\r\n", "\n").replace("\r", "\n")
    return re.split(r"\n\s*\n+", normalized_newlines)
