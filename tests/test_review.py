from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from crawler.review import (
    append_claim_review,
    create_claim_review,
    latest_reviews_by_claim,
    normalize_review_status,
    read_claim_reviews,
)


def test_create_claim_review_normalizes_status_and_keeps_notes_separate() -> None:
    review = create_claim_review(
        run_id="run-1",
        claim_id="claim-1",
        review_status="needs review",
        reviewer="analyst-a",
        notes="Confirm against original PDF before client delivery.",
        source_id="source-1",
        document_id="doc-1",
        reviewed_at="2026-06-04T12:00:00+00:00",
    )

    assert review.review_id.startswith("review-")
    assert review.review_status == "needs_review"
    assert review.notes == "Confirm against original PDF before client delivery."
    assert review.source_id == "source-1"


def test_review_status_validation_rejects_unknown_values() -> None:
    assert normalize_review_status("watchlisted") == "watchlisted"
    with pytest.raises(ValueError, match="review_status"):
        normalize_review_status("approved")


def test_append_read_and_latest_reviews_by_claim() -> None:
    first = create_claim_review(
        run_id="run-1",
        claim_id="claim-1",
        review_status="needs_review",
        reviewer="analyst-a",
        reviewed_at="2026-06-04T12:00:00+00:00",
    )
    second = create_claim_review(
        run_id="run-1",
        claim_id="claim-1",
        review_status="confirmed",
        reviewer="analyst-b",
        reviewed_at="2026-06-04T13:00:00+00:00",
    )

    with TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "claim_reviews.jsonl"
        append_claim_review(path, first)
        append_claim_review(path, second)
        reviews = read_claim_reviews(path)

    latest = latest_reviews_by_claim(reviews)

    assert [review.review_status for review in reviews] == ["needs_review", "confirmed"]
    assert latest["claim-1"].review_status == "confirmed"
    assert latest["claim-1"].reviewer == "analyst-b"
