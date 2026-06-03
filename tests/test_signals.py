from crawler.models import RedactedDocument
from crawler.signals import (
    extract_claims,
    extract_entities,
    extract_signal_batch,
    extract_signals,
    signal_log_entry,
)


def redacted_document(text: str) -> RedactedDocument:
    return RedactedDocument(
        document_id="doc-001",
        redacted_text=text,
        redaction_method="regex_redaction_v1",
        redaction_count=0,
    )


def test_extract_entities_finds_dictionary_terms_and_dates() -> None:
    entities = extract_entities(
        redacted_document(
            "BP Azerbaijan reported methane emissions near the Sangachal terminal in 2025.",
        ),
    )

    pairs = {(entity.entity_type, entity.normalized_text) for entity in entities}
    assert ("organization", "bp") in pairs
    assert ("organization", "bp azerbaijan") in pairs
    assert ("risk_topic", "methane") in pairs
    assert ("asset", "sangachal terminal") in pairs
    assert ("date", "2025") in pairs
    assert all(entity.evidence_excerpt for entity in entities)


def test_extract_claims_returns_evidence_and_attached_entities() -> None:
    document = redacted_document(
        "Global Witness reported gas flaring pollution in Azerbaijan. "
        "This sentence has no configured signal.",
    )
    entities = extract_entities(document)
    claims = extract_claims(document, entities)

    assert len(claims) == 1
    assert claims[0].claim_type == "environmental_risk"
    assert claims[0].evidence_excerpt == claims[0].claim_text
    assert claims[0].entities
    assert claims[0].extraction_method == "regex_dictionary_v1"


def test_extract_signals_allows_zero_entities_and_claims() -> None:
    extraction = extract_signals(redacted_document("Plain text without configured terms."))

    assert extraction.entities == []
    assert extraction.claims == []
    assert signal_log_entry(extraction)["claim_count"] == 0


def test_extract_signal_batch_preserves_one_result_per_document() -> None:
    results = extract_signal_batch(
        [
            redacted_document("SOCAR operates a field."),
            redacted_document("No configured terms."),
        ],
    )

    assert len(results) == 2
    assert results[0].entities
    assert results[1].entities == []
