"""Transparent entity and claim extraction from redacted documents.

This module intentionally starts with explainable dictionaries and regular
expressions. The goal is not perfect NLP; it is to produce auditable candidate
entities and claims that can be scored, cited, reviewed, and improved later.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import hashlib
import re

from crawler.models import Claim, Entity, RedactedDocument


EXTRACTION_METHOD = "regex_dictionary_v1"

ENTITY_DICTIONARIES = {
    "organization": (
        "SOCAR",
        "BP",
        "BP Azerbaijan",
        "ExxonMobil",
        "World Bank",
        "EITI",
        "Global Witness",
        "Human Rights Watch",
        "Amnesty International",
    ),
    "asset": (
        "Sangachal terminal",
        "Baku-Tbilisi-Ceyhan pipeline",
        "Oil Rocks",
        "Shah Deniz",
        "Azeri-Chirag-Gunashli",
    ),
    "location": (
        "Azerbaijan",
        "Caspian Sea",
        "Baku",
        "United States",
        "Texas",
    ),
    "risk_topic": (
        "gas flaring",
        "methane",
        "oil spill",
        "oil pollution",
        "corruption",
        "human rights",
        "labor",
        "sanctions",
        "emissions",
    ),
}

DATE_PATTERN = re.compile(r"\b(?:20\d{2}|19\d{2})\b")
SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")

CLAIM_KEYWORDS = {
    "environmental_risk": (
        "pollution",
        "spill",
        "flaring",
        "methane",
        "emissions",
        "contamination",
    ),
    "governance_risk": ("corruption", "transparency", "sanctions", "governance"),
    "labor_human_rights_risk": ("labor", "human rights", "community", "health"),
    "operational_context": ("pipeline", "terminal", "field", "production"),
}


@dataclass(slots=True)
class SignalExtraction:
    """Bundle entities and claims extracted from one redacted document.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        document_id (str): Stored value named ``document_id`` that travels with this
            record.
        entities (list[Entity]): Stored value named ``entities`` that travels with this
            record.
        claims (list[Claim]): Claim records extracted from cleaned and redacted
            documents.
    """
    document_id: str
    entities: list[Entity]
    claims: list[Claim]


def extract_signals(document: RedactedDocument) -> SignalExtraction:
    """Extract entities and claims from one redacted document."""
    entities = extract_entities(document)
    claims = extract_claims(document, entities)
    return SignalExtraction(document.document_id, entities, claims)


def extract_signal_batch(
    documents: Iterable[RedactedDocument],
) -> list[SignalExtraction]:
    """Extract entities and claims from many redacted documents."""
    return [extract_signals(document) for document in documents]


def extract_entities(document: RedactedDocument) -> list[Entity]:
    """Extract dictionary and year entities from redacted text."""
    entities: list[Entity] = []
    seen: set[tuple[str, str]] = set()
    text = document.redacted_text

    for entity_type, terms in ENTITY_DICTIONARIES.items():
        for term in terms:
            pattern = re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE)
            for match in pattern.finditer(text):
                normalized = term.casefold()
                key = (entity_type, normalized)
                if key in seen:
                    continue
                seen.add(key)
                entities.append(
                    _entity(
                        document,
                        entity_type,
                        match.group(0),
                        normalized,
                        text,
                        match.start(),
                        confidence=0.9,
                    ),
                )

    for match in DATE_PATTERN.finditer(text):
        normalized = match.group(0)
        key = ("date", normalized)
        if key in seen:
            continue
        seen.add(key)
        entities.append(
            _entity(
                document,
                "date",
                match.group(0),
                normalized,
                text,
                match.start(),
                confidence=0.8,
            ),
        )

    return entities


def extract_claims(
    document: RedactedDocument,
    entities: list[Entity] | None = None,
) -> list[Claim]:
    """Extract simple risk/context claims from redacted text sentences."""
    entity_list = entities if entities is not None else extract_entities(document)
    claims: list[Claim] = []

    for sentence in _sentences(document.redacted_text):
        claim_type = _claim_type(sentence)
        if claim_type is None:
            continue
        sentence_entities = _entities_in_text(entity_list, sentence)
        claims.append(
            Claim(
                claim_id=_stable_id("claim", document.document_id, claim_type, sentence),
                document_id=document.document_id,
                claim_text=sentence,
                claim_type=claim_type,
                entities=[entity.to_dict() for entity in sentence_entities],
                evidence_excerpt=sentence[:500],
                extraction_method=EXTRACTION_METHOD,
                confidence=0.7 if sentence_entities else 0.5,
                metadata={"entity_count": len(sentence_entities)},
            ),
        )

    return claims


def signal_log_entry(extraction: SignalExtraction) -> dict[str, object]:
    """Create a structured log entry for signal extraction output."""
    return {
        "stage": "extract_entities_claims",
        "document_id": extraction.document_id,
        "entity_count": len(extraction.entities),
        "claim_count": len(extraction.claims),
        "extraction_method": EXTRACTION_METHOD,
    }


def _entity(
    document: RedactedDocument,
    entity_type: str,
    text_value: str,
    normalized: str,
    full_text: str,
    start: int,
    *,
    confidence: float,
) -> Entity:
    """Support the module's public workflow by computing entity.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        document (RedactedDocument): Document record being transformed by this helper.
        entity_type (str): Value named ``entity_type`` supplied by the caller for this
            pipeline step.
        text_value (str): Value named ``text_value`` supplied by the caller for this
            pipeline step.
        normalized (str): Value named ``normalized`` supplied by the caller for this
            pipeline step.
        full_text (str): Value named ``full_text`` supplied by the caller for this
            pipeline step.
        start (int): Value named ``start`` supplied by the caller for this pipeline
            step.
        confidence (float): Value named ``confidence`` supplied by the caller for this
            pipeline step.
    
    Returns:
        Entity: Result produced for the next pipeline step or caller.
    """
    return Entity(
        entity_id=_stable_id("entity", document.document_id, entity_type, normalized),
        document_id=document.document_id,
        entity_type=entity_type,
        entity_text=text_value,
        normalized_text=normalized,
        evidence_excerpt=_excerpt(full_text, start),
        confidence=confidence,
        metadata={"redaction_method": document.redaction_method},
    )


def _entities_in_text(entities: list[Entity], text: str) -> list[Entity]:
    """Support the module's public workflow by computing entities in text.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        entities (list[Entity]): Value named ``entities`` supplied by the caller for
            this pipeline step.
        text (str): Text content being parsed, cleaned, redacted, or searched.
    
    Returns:
        list[Entity]: Result produced for the next pipeline step or caller.
    """
    lowered = text.casefold()
    return [
        entity
        for entity in entities
        if entity.normalized_text.casefold() in lowered
        or entity.entity_text.casefold() in lowered
    ]


def _claim_type(sentence: str) -> str | None:
    """Support the module's public workflow by computing claim type.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        sentence (str): Value named ``sentence`` supplied by the caller for this
            pipeline step.
    
    Returns:
        str | None: Result produced for the next pipeline step or caller.
    """
    lowered = sentence.casefold()
    for claim_type, keywords in CLAIM_KEYWORDS.items():
        if any(keyword in lowered for keyword in keywords):
            return claim_type
    return None


def _sentences(text: str) -> list[str]:
    """Support the module's public workflow by computing sentences.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        text (str): Text content being parsed, cleaned, redacted, or searched.
    
    Returns:
        list[str]: Result produced for the next pipeline step or caller.
    """
    return [
        sentence.strip()
        for sentence in SENTENCE_SPLIT_PATTERN.split(text.replace("\n", " "))
        if sentence.strip()
    ]


def _excerpt(text: str, start: int, radius: int = 120) -> str:
    """Support the module's public workflow by computing excerpt.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        text (str): Text content being parsed, cleaned, redacted, or searched.
        start (int): Value named ``start`` supplied by the caller for this pipeline
            step.
        radius (int): Value named ``radius`` supplied by the caller for this pipeline
            step.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    begin = max(0, start - radius)
    end = min(len(text), start + radius)
    return re.sub(r"\s+", " ", text[begin:end]).strip()


def _stable_id(prefix: str, *parts: str) -> str:
    """Support the module's public workflow by computing stable id.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        prefix (str): Value named ``prefix`` supplied by the caller for this pipeline
            step.
        parts (str): Value named ``parts`` supplied by the caller for this pipeline
            step.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"
