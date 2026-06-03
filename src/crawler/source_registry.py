"""Source registry loading and validation."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from crawler.models import Source


REQUIRED_FIELDS = (
    "source_id",
    "name",
    "tier",
    "publisher_type",
    "base_url",
    "access_method",
    "rate_limit_seconds",
    "robots_required",
    "notes",
    "enabled",
)

LIST_FIELDS = {"allowed_paths", "blocked_paths", "domain_tags"}
BOOLEAN_FIELDS = {"robots_required", "enabled"}
FLOAT_FIELDS = {"rate_limit_seconds"}
SOURCE_FIELDS = {
    "source_id",
    "name",
    "tier",
    "publisher_type",
    "base_url",
    "access_method",
    "rate_limit_seconds",
    "robots_required",
    "enabled",
    "notes",
    "allowed_paths",
    "blocked_paths",
}


@dataclass(slots=True)
class RegistryIssue:
    row_number: int
    source_id: str | None
    field: str
    message: str


@dataclass(slots=True)
class SourceRegistry:
    sources: list[Source] = field(default_factory=list)
    skipped: list[Source] = field(default_factory=list)
    issues: list[RegistryIssue] = field(default_factory=list)

    @property
    def enabled_sources(self) -> list[Source]:
        return [source for source in self.sources if source.enabled]

    @property
    def has_errors(self) -> bool:
        return bool(self.issues)


class SourceRegistryError(ValueError):
    """Raised when a source registry contains invalid rows."""

    def __init__(self, issues: Iterable[RegistryIssue]) -> None:
        self.issues = list(issues)
        details = "; ".join(
            f"row {issue.row_number} {issue.field}: {issue.message}"
            for issue in self.issues
        )
        super().__init__(f"Invalid source registry: {details}")


def load_source_registry(
    path: str | Path = "data/sources.csv",
    *,
    include_disabled: bool = False,
    raise_on_error: bool = True,
) -> SourceRegistry:
    """Load and validate a CSV source registry."""
    registry_path = Path(path)
    registry = SourceRegistry()

    with registry_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing_columns = [field for field in REQUIRED_FIELDS if field not in fieldnames]
        if missing_columns:
            registry.issues.append(
                RegistryIssue(
                    row_number=0,
                    source_id=None,
                    field="header",
                    message=f"missing required columns: {', '.join(missing_columns)}",
                )
            )
            if raise_on_error:
                raise SourceRegistryError(registry.issues)
            return registry

        for row_number, row in enumerate(reader, start=2):
            source, issues = _parse_row(row_number, row)
            registry.issues.extend(issues)
            if source is None:
                continue
            if source.enabled or include_disabled:
                registry.sources.append(source)
            else:
                registry.skipped.append(source)

    if registry.issues and raise_on_error:
        raise SourceRegistryError(registry.issues)
    return registry


def _parse_row(
    row_number: int,
    row: dict[str, str | None],
) -> tuple[Source | None, list[RegistryIssue]]:
    issues: list[RegistryIssue] = []
    source_id = _clean(row.get("source_id"))

    for field_name in REQUIRED_FIELDS:
        if _clean(row.get(field_name)) == "":
            issues.append(
                RegistryIssue(
                    row_number=row_number,
                    source_id=source_id or None,
                    field=field_name,
                    message="required value is blank",
                )
            )

    parsed: dict[str, object] = {}
    for field_name, value in row.items():
        if field_name is None:
            continue
        try:
            parsed[field_name] = _parse_value(field_name, value)
        except ValueError as error:
            issues.append(
                RegistryIssue(
                    row_number=row_number,
                    source_id=source_id or None,
                    field=field_name,
                    message=str(error),
                )
            )

    if issues:
        return None, issues

    return (
        Source(
            source_id=str(parsed["source_id"]),
            name=str(parsed["name"]),
            tier=str(parsed["tier"]),
            publisher_type=str(parsed["publisher_type"]),
            base_url=str(parsed["base_url"]),
            access_method=str(parsed["access_method"]),
            rate_limit_seconds=parsed["rate_limit_seconds"],  # type: ignore[arg-type]
            robots_required=bool(parsed["robots_required"]),
            enabled=bool(parsed["enabled"]),
            notes=str(parsed["notes"]),
            allowed_paths=parsed.get("allowed_paths", []),  # type: ignore[arg-type]
            blocked_paths=parsed.get("blocked_paths", []),  # type: ignore[arg-type]
            metadata={
                key: value
                for key, value in parsed.items()
                if key not in SOURCE_FIELDS and value not in ("", None, [])
            },
        ),
        issues,
    )


def _parse_value(field_name: str, value: str | None) -> object:
    cleaned = _clean(value)
    if field_name in BOOLEAN_FIELDS:
        return _parse_bool(cleaned)
    if field_name in FLOAT_FIELDS:
        return float(cleaned)
    if field_name in LIST_FIELDS:
        return [item.strip() for item in cleaned.split("|") if item.strip()]
    return cleaned


def _parse_bool(value: str) -> bool:
    lowered = value.lower()
    if lowered in {"true", "1", "yes", "y"}:
        return True
    if lowered in {"false", "0", "no", "n"}:
        return False
    raise ValueError(f"expected boolean value, got {value!r}")


def _clean(value: str | None) -> str:
    return "" if value is None else value.strip()
