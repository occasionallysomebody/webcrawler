"""Controlled onboarding for proposed public sources.

Production crawling should not automatically trust every suggested URL. This
module keeps proposed sources separate from active crawling until reviewer
metadata, access settings, and approval status show that the source is safe to
promote into the registry.
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from crawler.models import Source
from crawler.source_registry import REQUIRED_FIELDS, load_source_registry


PROPOSAL_FIELDS = (
    "proposal_status",
    "proposed_by",
    "proposed_at",
    "reviewed_by",
    "reviewed_at",
    "review_notes",
)
VALID_STATUSES = {"proposed", "approved", "rejected"}
ACTIVE_METADATA_FIELDS = (
    "sitemap_url",
    "rss_url",
    "api_url",
    "language",
    "country",
    "domain_tags",
    "known_bias_or_limitation",
)
ACTIVE_FIELDS = (
    *REQUIRED_FIELDS[:8],
    "enabled",
    "notes",
    "sitemap_url",
    "rss_url",
    "api_url",
    "allowed_paths",
    "blocked_paths",
    "language",
    "country",
    "domain_tags",
    "known_bias_or_limitation",
)


@dataclass(slots=True)
class OnboardingIssue:
    """Describe a proposed-source onboarding problem in a structured way.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        source_id (str): Stable source identifier used to connect documents, claims, and
            scores.
        field (str): Stored value named ``field`` that travels with this record.
        message (str): Stored value named ``message`` that travels with this record.
    """
    source_id: str
    field: str
    message: str


@dataclass(slots=True)
class ProposedSource:
    """Represent a source proposal before it is allowed into active crawling.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        source (Source): Source registry entry that explains where a document or URL
            came from.
        proposal_status (str): Stored value named ``proposal_status`` that travels with
            this record.
        proposed_by (str): Stored value named ``proposed_by`` that travels with this
            record.
        proposed_at (str): Stored value named ``proposed_at`` that travels with this
            record.
        reviewed_by (str): Stored value named ``reviewed_by`` that travels with this
            record.
        reviewed_at (str): Stored value named ``reviewed_at`` that travels with this
            record.
        review_notes (str): Stored value named ``review_notes`` that travels with this
            record.
    """
    source: Source
    proposal_status: str
    proposed_by: str
    proposed_at: str
    reviewed_by: str = ""
    reviewed_at: str = ""
    review_notes: str = ""


@dataclass(slots=True)
class OnboardingReport:
    """Collect source-onboarding issues and promotion results.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        proposed_count (int): Stored value named ``proposed_count`` that travels with
            this record.
        approved_count (int): Stored value named ``approved_count`` that travels with
            this record.
        promoted_count (int): Stored value named ``promoted_count`` that travels with
            this record.
        skipped_existing (list[str]): Stored value named ``skipped_existing`` that
            travels with this record.
        rejected_count (int): Stored value named ``rejected_count`` that travels with
            this record.
        pending_count (int): Stored value named ``pending_count`` that travels with this
            record.
        issues (list[OnboardingIssue]): Stored value named ``issues`` that travels with
            this record.
    """
    proposed_count: int
    approved_count: int
    promoted_count: int
    skipped_existing: list[str] = field(default_factory=list)
    rejected_count: int = 0
    pending_count: int = 0
    issues: list[OnboardingIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        """Report whether the validation result contains blocking errors.
        
        The pipeline is intentionally split into small steps so a junior developer can
        inspect each artifact and understand why the next stage received its input.
        
        Returns:
            bool: Boolean decision used by the caller to choose the next pipeline step.
        """
        return bool(self.issues)


class OnboardingError(ValueError):
    """Raised when proposed source onboarding fails validation."""

    def __init__(self, issues: list[OnboardingIssue]) -> None:
        """Initialize the object and keep its stored state explicit.
        
        This private helper keeps the public function small and testable. It is
        documented because new maintainers often need to inspect these helpers when
        debugging a crawl run.
        
        Args:
            issues (list[OnboardingIssue]): Value named ``issues`` supplied by the
                caller for this pipeline step.
        
        Returns:
            None: This function is used for its side effect and does not return a value.
        """
        self.issues = issues
        details = "; ".join(
            f"{issue.source_id} {issue.field}: {issue.message}" for issue in issues
        )
        super().__init__(f"Invalid proposed sources: {details}")


def load_proposed_sources(path: str | Path) -> list[ProposedSource]:
    """Load proposed sources from a separate proposal CSV."""
    registry = load_source_registry(path, include_disabled=True)
    proposed = [_proposed_source(source) for source in registry.sources]
    issues = validate_proposed_sources(proposed)
    if issues:
        raise OnboardingError(issues)
    return proposed


def validate_proposed_sources(
    proposals: list[ProposedSource],
) -> list[OnboardingIssue]:
    """Validate proposal status and approval metadata."""
    issues: list[OnboardingIssue] = []
    for proposal in proposals:
        source = proposal.source
        if proposal.proposal_status not in VALID_STATUSES:
            issues.append(
                OnboardingIssue(
                    source.source_id,
                    "proposal_status",
                    f"expected one of {sorted(VALID_STATUSES)}",
                )
            )
        if not proposal.proposed_by:
            issues.append(
                OnboardingIssue(source.source_id, "proposed_by", "required"),
            )
        if not proposal.proposed_at:
            issues.append(
                OnboardingIssue(source.source_id, "proposed_at", "required"),
            )
        if proposal.proposal_status == "approved":
            if not proposal.reviewed_by:
                issues.append(
                    OnboardingIssue(source.source_id, "reviewed_by", "required"),
                )
            if not proposal.reviewed_at:
                issues.append(
                    OnboardingIssue(source.source_id, "reviewed_at", "required"),
                )
            if source.access_method == "manual_review":
                issues.append(
                    OnboardingIssue(
                        source.source_id,
                        "access_method",
                        "approved sources must have a crawlable access method",
                    )
                )
            if source.rate_limit_seconds is None or source.rate_limit_seconds < 1:
                issues.append(
                    OnboardingIssue(
                        source.source_id,
                        "rate_limit_seconds",
                        "approved sources require a conservative rate limit >= 1",
                    )
                )
    return issues


def promote_approved_sources(
    *,
    proposed_path: str | Path,
    active_path: str | Path = "data/sources.csv",
    output_path: str | Path | None = None,
) -> OnboardingReport:
    """Promote approved proposals into the active source registry CSV."""
    proposals = load_proposed_sources(proposed_path)
    active_rows = _read_rows(active_path)
    active_ids = {row.get("source_id", "") for row in active_rows}
    promoted_rows: list[dict[str, str]] = []
    skipped_existing: list[str] = []

    for proposal in proposals:
        source = proposal.source
        if proposal.proposal_status != "approved":
            continue
        if source.source_id in active_ids:
            skipped_existing.append(source.source_id)
            continue
        promoted_rows.append(_active_row(proposal))
        active_ids.add(source.source_id)

    destination = Path(output_path) if output_path is not None else Path(active_path)
    _write_rows(destination, [*active_rows, *promoted_rows])
    return OnboardingReport(
        proposed_count=len(proposals),
        approved_count=sum(1 for proposal in proposals if proposal.proposal_status == "approved"),
        promoted_count=len(promoted_rows),
        skipped_existing=skipped_existing,
        rejected_count=sum(1 for proposal in proposals if proposal.proposal_status == "rejected"),
        pending_count=sum(1 for proposal in proposals if proposal.proposal_status == "proposed"),
    )


def write_proposed_source_template(path: str | Path) -> Path:
    """Write an empty proposed-source template CSV."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=[*ACTIVE_FIELDS, *PROPOSAL_FIELDS])
        writer.writeheader()
    return target


def onboarding_log_entry(report: OnboardingReport) -> dict[str, Any]:
    """Create a structured log-style summary for onboarding actions."""
    return {
        "stage": "source_onboarding",
        "proposed_count": report.proposed_count,
        "approved_count": report.approved_count,
        "promoted_count": report.promoted_count,
        "rejected_count": report.rejected_count,
        "pending_count": report.pending_count,
        "skipped_existing": report.skipped_existing,
    }


def main(argv: list[str] | None = None) -> int:
    """Run the module's command-line interface.
    
    The pipeline is intentionally split into small steps so a junior developer can
    inspect each artifact and understand why the next stage received its input.
    
    Args:
        argv (list[str] | None): Optional command-line arguments. When omitted, Python
            uses the process arguments.
    
    Returns:
        int: Integer count or process exit code.
    """
    parser = argparse.ArgumentParser(description="Manage source onboarding.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    template = subparsers.add_parser("template", help="Write proposal CSV template.")
    template.add_argument("--path", default="data/proposed_sources.csv")

    validate = subparsers.add_parser("validate", help="Validate proposed sources.")
    validate.add_argument("--proposed", default="data/proposed_sources.csv")

    promote = subparsers.add_parser("promote", help="Promote approved sources.")
    promote.add_argument("--proposed", default="data/proposed_sources.csv")
    promote.add_argument("--active", default="data/sources.csv")
    promote.add_argument("--output")

    args = parser.parse_args(argv)
    if args.command == "template":
        print(write_proposed_source_template(args.path))
        return 0
    if args.command == "validate":
        proposals = load_proposed_sources(args.proposed)
        print(f"valid proposed sources: {len(proposals)}")
        return 0
    report = promote_approved_sources(
        proposed_path=args.proposed,
        active_path=args.active,
        output_path=args.output,
    )
    print(onboarding_log_entry(report))
    return 0


def _proposed_source(source: Source) -> ProposedSource:
    """Support the module's public workflow by computing proposed source.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        source (Source): Source registry entry that explains where a document or URL
            came from.
    
    Returns:
        ProposedSource: Result produced for the next pipeline step or caller.
    """
    metadata = source.metadata
    return ProposedSource(
        source=source,
        proposal_status=str(metadata.get("proposal_status", "")).strip(),
        proposed_by=str(metadata.get("proposed_by", "")).strip(),
        proposed_at=str(metadata.get("proposed_at", "")).strip(),
        reviewed_by=str(metadata.get("reviewed_by", "")).strip(),
        reviewed_at=str(metadata.get("reviewed_at", "")).strip(),
        review_notes=str(metadata.get("review_notes", "")).strip(),
    )


def _read_rows(path: str | Path) -> list[dict[str, str]]:
    """Support the module's public workflow by computing read rows.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        path (str | Path): Filesystem path used by this step. It may be a string or a
            ``Path`` depending on the caller.
    
    Returns:
        list[dict[str, str]]: Result produced for the next pipeline step or caller.
    """
    source = Path(path)
    if not source.exists():
        return []
    with source.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    """Support the module's public workflow by computing write rows.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        path (Path): Filesystem path used by this step. It may be a string or a ``Path``
            depending on the caller.
        rows (list[dict[str, str]]): CSV rows or record dictionaries being written or
            validated.
    
    Returns:
        None: This function is used for its side effect and does not return a value.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(ACTIVE_FIELDS))
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ACTIVE_FIELDS})


def _active_row(proposal: ProposedSource) -> dict[str, str]:
    """Support the module's public workflow by computing active row.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        proposal (ProposedSource): Value named ``proposal`` supplied by the caller for
            this pipeline step.
    
    Returns:
        dict[str, str]: Result produced for the next pipeline step or caller.
    """
    source = proposal.source
    metadata = source.metadata
    notes = source.notes
    if proposal.review_notes:
        notes = f"{notes} Onboarding review: {proposal.review_notes}".strip()
    return {
        "source_id": source.source_id,
        "name": source.name,
        "tier": source.tier,
        "publisher_type": source.publisher_type,
        "base_url": source.base_url,
        "access_method": source.access_method,
        "rate_limit_seconds": _csv_value(source.rate_limit_seconds),
        "robots_required": str(source.robots_required).lower(),
        "enabled": "true",
        "notes": notes,
        "allowed_paths": "|".join(source.allowed_paths),
        "blocked_paths": "|".join(source.blocked_paths),
        **{field: _csv_value(metadata.get(field, "")) for field in ACTIVE_METADATA_FIELDS},
    }


def _csv_value(value: Any) -> str:
    """Support the module's public workflow by computing csv value.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        value (Any): Raw value being normalized or converted into a typed
            representation.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    if isinstance(value, list):
        return "|".join(str(item) for item in value)
    if value is None:
        return ""
    return str(value)


def default_proposed_at() -> str:
    """Return a timestamp suitable for proposed source templates."""
    return datetime.now(UTC).isoformat()


if __name__ == "__main__":
    raise SystemExit(main())
