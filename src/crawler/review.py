"""Analyst review workflow helpers for extracted claims.

The crawler keeps extracted evidence immutable. Human decisions are stored as
separate append-only review records so an export can show both the source claim
and the analyst's current assessment.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
import json
from uuid import uuid4
from typing import Any

from crawler.models import ClaimReview
from crawler.storage import append_jsonl, read_jsonl


REVIEW_STATUSES = {"confirmed", "rejected", "needs_review", "watchlisted"}


def normalize_review_status(value: str) -> str:
    """Normalize and validate a human review status."""

    normalized = str(value).strip().lower().replace(" ", "_").replace("-", "_")
    if normalized not in REVIEW_STATUSES:
        allowed = ", ".join(sorted(REVIEW_STATUSES))
        raise ValueError(f"review_status must be one of: {allowed}")
    return normalized


def create_claim_review(
    *,
    run_id: str,
    claim_id: str,
    review_status: str,
    reviewer: str,
    notes: str = "",
    source_id: str | None = None,
    document_id: str | None = None,
    metadata: dict[str, Any] | None = None,
    reviewed_at: str | None = None,
) -> ClaimReview:
    """Create one normalized claim review record."""

    safe_metadata = metadata or {}
    try:
        json.dumps(safe_metadata, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError("review metadata must be JSON serializable") from error
    cleaned_reviewer = str(reviewer or "authenticated-analyst").strip()
    if not cleaned_reviewer:
        cleaned_reviewer = "authenticated-analyst"
    cleaned_claim_id = str(claim_id).strip()
    if not cleaned_claim_id:
        raise ValueError("claim_id is required")
    cleaned_run_id = str(run_id).strip()
    if not cleaned_run_id:
        raise ValueError("run_id is required")
    return ClaimReview(
        review_id=f"review-{uuid4().hex}",
        run_id=cleaned_run_id,
        claim_id=cleaned_claim_id,
        review_status=normalize_review_status(review_status),
        reviewer=cleaned_reviewer[:120],
        reviewed_at=reviewed_at or datetime.now(UTC).isoformat(),
        notes=str(notes or "").strip()[:4000],
        source_id=_optional_text(source_id),
        document_id=_optional_text(document_id),
        metadata=safe_metadata,
    )


def append_claim_review(path: str | Path, review: ClaimReview) -> ClaimReview:
    """Append one review record to JSONL and return it."""

    append_jsonl(path, [review])
    return review


def read_claim_reviews(path: str | Path) -> list[ClaimReview]:
    """Read review records from JSONL, ignoring malformed legacy rows."""

    reviews = []
    for payload in read_jsonl(path):
        try:
            reviews.append(ClaimReview(**payload))
        except TypeError:
            continue
    return reviews


def latest_reviews_by_claim(
    reviews: Iterable[ClaimReview],
) -> dict[str, ClaimReview]:
    """Return the latest review decision for each claim."""

    latest: dict[str, ClaimReview] = {}
    for review in reviews:
        current = latest.get(review.claim_id)
        if current is None or review.reviewed_at >= current.reviewed_at:
            latest[review.claim_id] = review
    return latest


def review_to_public_dict(review: ClaimReview) -> dict[str, Any]:
    """Return the review fields safe for API and UI display."""

    return {
        "review_id": review.review_id,
        "run_id": review.run_id,
        "claim_id": review.claim_id,
        "review_status": review.review_status,
        "reviewer": review.reviewer,
        "reviewed_at": review.reviewed_at,
        "notes": review.notes,
        "source_id": review.source_id,
        "document_id": review.document_id,
        "metadata": review.metadata,
    }


def _optional_text(value: str | None) -> str | None:
    """Return trimmed optional text."""

    if value is None:
        return None
    cleaned = str(value).strip()
    return cleaned or None
