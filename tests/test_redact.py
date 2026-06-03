from crawler.models import CleanDocument
from crawler.redact import (
    redact_document,
    redact_documents,
    redaction_log_entry,
)


def clean_document(text: str) -> CleanDocument:
    return CleanDocument(
        document_id="doc-001",
        clean_text=text,
        cleaning_method="normalize_whitespace_v1",
        word_count=len(text.split()),
        language="en",
        quality_flags=["fixture"],
    )


def test_redact_document_replaces_email_phone_and_address() -> None:
    document = clean_document(
        "Contact jane.doe@example.org or +1 (202) 555-0181.\n\n"
        "Mail should not be sent to 123 Main Street, Springfield, VA 22101.",
    )

    redacted = redact_document(document)

    assert "jane.doe@example.org" not in redacted.redacted_text
    assert "(202) 555-0181" not in redacted.redacted_text
    assert "123 Main Street" not in redacted.redacted_text
    assert "[REDACTED_EMAIL]" in redacted.redacted_text
    assert "[REDACTED_PHONE]" in redacted.redacted_text
    assert "[REDACTED_ADDRESS]" in redacted.redacted_text
    assert redacted.redaction_count == 3
    assert redacted.redaction_types == ["email", "phone", "address"]
    assert redacted.metadata["redaction_counts_by_type"] == {
        "email": 1,
        "phone": 1,
        "address": 1,
    }


def test_redact_document_preserves_text_without_sensitive_patterns() -> None:
    document = clean_document("Public report text about energy operations.")

    redacted = redact_document(document)

    assert redacted.redacted_text == document.clean_text
    assert redacted.redaction_count == 0
    assert redacted.redaction_types == []


def test_redact_document_redacts_multiple_instances_and_keeps_source_metadata() -> None:
    document = clean_document(
        "Email alpha@example.org, beta@example.org, or call 202-555-0100.",
    )

    redacted = redact_document(document)

    assert redacted.redaction_count == 3
    assert redacted.redacted_text.count("[REDACTED_EMAIL]") == 2
    assert redacted.redacted_text.count("[REDACTED_PHONE]") == 1
    assert redacted.metadata["source_cleaning_method"] == "normalize_whitespace_v1"
    assert redacted.metadata["source_quality_flags"] == ["fixture"]


def test_redact_documents_preserves_one_output_per_input_and_logs() -> None:
    redacted = redact_documents(
        [
            clean_document("Email alpha@example.org."),
            clean_document("No sensitive text."),
        ],
    )

    assert len(redacted) == 2
    assert redacted[0].redaction_count == 1
    assert redacted[1].redaction_count == 0
    assert redaction_log_entry(redacted[0]) == {
        "stage": "redact_sensitive_data",
        "document_id": "doc-001",
        "redaction_method": "regex_redaction_v1",
        "redaction_count": 1,
        "redaction_types": ["email"],
    }
