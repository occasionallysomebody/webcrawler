"""Audit-event helpers for analyst-facing API actions.

Audit logs let a reviewer reconstruct who selected a run, inspected evidence,
or exported claim packets. The helpers write small JSONL records and avoid
storing raw document text in the audit trail.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import re
from uuid import uuid4
from typing import Any

from crawler.models import AuditEvent
from crawler.storage import append_jsonl


_TOKEN_RE = re.compile(r"[^A-Za-z0-9_.:@-]+")


def create_audit_event(
    *,
    event_type: str,
    actor: str,
    run_id: str | None = None,
    claim_id: str | None = None,
    document_id: str | None = None,
    source_id: str | None = None,
    request_path: str | None = None,
    metadata: dict[str, Any] | None = None,
    created_at: str | None = None,
) -> AuditEvent:
    """Create a normalized audit event.

    Args:
        event_type (str): Short action name such as ``evidence_exported``.
        actor (str): Analyst or service account label.
        run_id (str | None): Run touched by the action.
        claim_id (str | None): Claim touched by the action.
        document_id (str | None): Document touched by the action.
        source_id (str | None): Source touched by the action.
        request_path (str | None): API path that recorded the action.
        metadata (dict[str, Any] | None): Small JSON-safe details about the
            action. Raw evidence text should not be placed here.
        created_at (str | None): Optional timestamp for deterministic tests.

    Returns:
        AuditEvent: Serializable audit record ready for JSONL storage.

    Raises:
        ValueError: Raised when required values are blank or metadata cannot be
            JSON serialized.
    """

    normalized_event_type = _token(event_type, field_name="event_type")
    normalized_actor = _actor(actor)
    safe_metadata = _metadata(metadata or {})
    timestamp = created_at or datetime.now(UTC).isoformat()
    return AuditEvent(
        event_id=f"audit-{uuid4().hex}",
        event_type=normalized_event_type,
        actor=normalized_actor,
        created_at=timestamp,
        run_id=_optional_token(run_id),
        claim_id=_optional_token(claim_id),
        document_id=_optional_token(document_id),
        source_id=_optional_token(source_id),
        request_path=request_path,
        metadata=safe_metadata,
    )


def append_audit_event(path: str | Path, event: AuditEvent) -> AuditEvent:
    """Append one audit event to a JSONL audit log.

    Args:
        path (str | Path): Destination JSONL path.
        event (AuditEvent): Event to append.

    Returns:
        AuditEvent: The same event, returned for convenient API responses.
    """

    append_jsonl(path, [event])
    return event


def record_audit_event(path: str | Path, **kwargs: Any) -> AuditEvent:
    """Create and append an audit event in one call.

    Args:
        path (str | Path): Destination JSONL path.
        kwargs (Any): Keyword arguments accepted by ``create_audit_event``.

    Returns:
        AuditEvent: Event that was written to disk.
    """

    return append_audit_event(path, create_audit_event(**kwargs))


def _token(value: str, *, field_name: str) -> str:
    """Normalize a required audit token.

    Args:
        value (str): Raw token value.
        field_name (str): Field name used in error messages.

    Returns:
        str: Normalized token value.

    Raises:
        ValueError: Raised when the token is blank.
    """

    cleaned = _TOKEN_RE.sub("_", str(value).strip())[:120].strip("_")
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    return cleaned


def _optional_token(value: str | None) -> str | None:
    """Normalize an optional audit token.

    Args:
        value (str | None): Raw token value.

    Returns:
        str | None: Normalized token or ``None`` when blank.
    """

    if value is None or str(value).strip() == "":
        return None
    return _token(str(value), field_name="token")


def _actor(value: str) -> str:
    """Normalize an audit actor label.

    Args:
        value (str): Raw analyst or service account label.

    Returns:
        str: Normalized actor label.
    """

    return _token(value or "authenticated-analyst", field_name="actor")


def _metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Validate that audit metadata is JSON-safe.

    Args:
        value (dict[str, Any]): Metadata supplied by API or UI callers.

    Returns:
        dict[str, Any]: Metadata that can be serialized to JSON.

    Raises:
        ValueError: Raised when the metadata cannot be serialized.
    """

    try:
        json.dumps(value, sort_keys=True)
    except (TypeError, ValueError) as error:
        raise ValueError("audit metadata must be JSON serializable") from error
    return value
