"""Redaction rules for unnecessary sensitive text."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import re

from crawler.models import CleanDocument, RedactedDocument


REDACTION_METHOD = "regex_redaction_v1"


@dataclass(frozen=True, slots=True)
class RedactionRule:
    redaction_type: str
    placeholder: str
    pattern: re.Pattern[str]


REDACTION_RULES = (
    RedactionRule(
        redaction_type="email",
        placeholder="[REDACTED_EMAIL]",
        pattern=re.compile(
            r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b",
            re.IGNORECASE,
        ),
    ),
    RedactionRule(
        redaction_type="phone",
        placeholder="[REDACTED_PHONE]",
        pattern=re.compile(
            r"""
            (?<!\w)
            (?:\+?1[\s.-]?)?
            (?:\(\d{3}\)|\d{3})
            [\s.-]?
            \d{3}
            [\s.-]?
            \d{4}
            (?!\w)
            """,
            re.VERBOSE,
        ),
    ),
    RedactionRule(
        redaction_type="address",
        placeholder="[REDACTED_ADDRESS]",
        pattern=re.compile(
            r"""
            \b
            \d{1,6}
            \s+
            (?:[A-Z][A-Za-z0-9'.-]*\s+){1,6}
            (?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|
               Drive|Dr\.?|Lane|Ln\.?|Way|Court|Ct\.?)
            \b
            (?:,\s*[A-Z][A-Za-z .'-]+)?
            (?:,\s*[A-Z]{2})?
            (?:\s+\d{5}(?:-\d{4})?)?
            """,
            re.IGNORECASE | re.VERBOSE,
        ),
    ),
)


def redact_document(document: CleanDocument) -> RedactedDocument:
    """Redact unnecessary sensitive text from one clean document."""
    redacted_text = document.clean_text
    counts_by_type: dict[str, int] = {}

    for rule in REDACTION_RULES:
        redacted_text, count = rule.pattern.subn(rule.placeholder, redacted_text)
        if count:
            counts_by_type[rule.redaction_type] = count

    redaction_types = list(counts_by_type)
    redaction_count = sum(counts_by_type.values())
    return RedactedDocument(
        document_id=document.document_id,
        redacted_text=redacted_text,
        redaction_method=REDACTION_METHOD,
        redaction_count=redaction_count,
        redaction_types=redaction_types,
        metadata={
            "source_cleaning_method": document.cleaning_method,
            "source_word_count": document.word_count,
            "source_language": document.language,
            "source_quality_flags": list(document.quality_flags),
            "redaction_counts_by_type": counts_by_type,
        },
    )


def redact_documents(
    documents: Iterable[CleanDocument],
) -> list[RedactedDocument]:
    """Redact many clean documents, preserving one output per input."""
    return [redact_document(document) for document in documents]


def redaction_log_entry(document: RedactedDocument) -> dict[str, object]:
    """Create a structured log entry for redaction output."""
    return {
        "stage": "redact_sensitive_data",
        "document_id": document.document_id,
        "redaction_method": document.redaction_method,
        "redaction_count": document.redaction_count,
        "redaction_types": document.redaction_types,
    }
