from crawler.clean import (
    clean_document,
    clean_documents,
    cleaning_log_entry,
    count_words,
    detect_language,
    is_boilerplate,
    normalize_paragraphs,
    normalize_whitespace,
)
from crawler.models import ExtractedDocument


def extracted_document(
    text: str,
    *,
    error: str | None = None,
) -> ExtractedDocument:
    return ExtractedDocument(
        document_id="doc-001",
        source_id="example-source",
        url="https://example.org/report",
        title="Example report",
        published_at="2026-06-03",
        extracted_text=text,
        extraction_method="html",
        extraction_quality="medium",
        error=error,
    )


def test_clean_document_normalizes_whitespace_and_preserves_paragraphs() -> None:
    extracted = extracted_document(
        " First   paragraph with   spacing.\n\nSecond\tparagraph with context. ",
    )

    cleaned = clean_document(extracted)

    assert cleaned.clean_text == (
        "First paragraph with spacing.\n\nSecond paragraph with context."
    )
    assert cleaned.cleaning_method == "normalize_whitespace_v1"
    assert cleaned.word_count == 8
    assert cleaned.language == "en"
    assert "short_text" in cleaned.quality_flags
    assert cleaned.metadata["source_url"] == "https://example.org/report"
    assert extracted.extracted_text.startswith(" First")


def test_clean_document_removes_obvious_boilerplate_and_adjacent_duplicates() -> None:
    extracted = extracted_document(
        "Accept all cookies\n\n"
        "Energy operations are described with enough useful evidence for review.\n\n"
        "Energy operations are described with enough useful evidence for review.\n\n"
        "Share this article",
    )

    cleaned = clean_document(extracted)

    assert cleaned.clean_text == (
        "Energy operations are described with enough useful evidence for review."
    )
    assert "boilerplate_removed" in cleaned.quality_flags
    assert "duplicate_paragraphs_removed" in cleaned.quality_flags
    assert cleaned.metadata["removed_boilerplate_paragraphs"] == 2
    assert cleaned.metadata["removed_duplicate_paragraphs"] == 1


def test_clean_document_records_empty_and_error_inputs() -> None:
    cleaned = clean_document(extracted_document("   ", error="empty_extraction"))

    assert cleaned.clean_text == ""
    assert cleaned.word_count == 0
    assert "source_extraction_error" in cleaned.quality_flags
    assert "empty_input" in cleaned.quality_flags


def test_clean_documents_preserves_one_output_per_input_and_logs() -> None:
    cleaned = clean_documents(
        [
            extracted_document("First document text."),
            extracted_document("Second document text."),
        ],
    )

    assert len(cleaned) == 2
    assert cleaning_log_entry(cleaned[0])["stage"] == "clean_text"
    assert cleaning_log_entry(cleaned[0])["word_count"] == 3


def test_normalization_helpers_are_deterministic() -> None:
    paragraphs, removed_count, duplicate_count = normalize_paragraphs(
        "Menu\n\nUseful text.\n\nUseful text.\n\nPrivacy policy",
    )

    assert normalize_whitespace(" a\t b \n c ") == "a b\nc"
    assert paragraphs == ["Useful text."]
    assert removed_count == 2
    assert duplicate_count == 1
    assert is_boilerplate("Subscribe to our newsletter")
    assert not is_boilerplate("This paragraph contains substantive evidence.")
    assert count_words("Oil-and-gas evidence, reviewed.") == 3


def test_detect_language_returns_simple_hints() -> None:
    assert detect_language("This is an English sentence.") == "en"
    assert detect_language("Это русский текст.") == "ru"
    assert detect_language("12345") is None
