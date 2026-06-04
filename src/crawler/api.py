"""FastAPI service over crawler run artifacts.

The API is the production-facing boundary for the proof of concept. It reads
auditable run artifacts from a configured storage path, serves the map-data
contract used by the frontend, rejects unauthenticated data requests when auth
is enabled, and records analyst audit events for evidence-sensitive actions.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
import secrets
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from crawler.audit import record_audit_event
from crawler.config import (
    DeploymentSettings,
    load_deployment_settings,
    validate_deployment_settings,
)
from crawler.map_ui import MapUiRecords, build_map_data, load_map_records, render_map_html
from crawler.models import Claim, ClaimReview, FetchedDocument, Source, TrustScore
from crawler.review import (
    append_claim_review,
    create_claim_review,
    latest_reviews_by_claim,
    read_claim_reviews,
    review_to_public_dict,
)
from crawler.storage import (
    fetch_run_records,
    fetch_run_summary,
    initialize_sqlite,
    list_run_summaries,
    read_jsonl,
    upsert_audit_event,
    upsert_run_records,
)


RECORD_ALLOWLIST = {
    "sources": "sources.jsonl",
    "discovered_items": "discovered_items.jsonl",
    "access_decisions": "access_decisions.jsonl",
    "fetched_documents": "fetched_documents.jsonl",
    "extracted_documents": "extracted_documents.jsonl",
    "clean_documents": "clean_documents.jsonl",
    "redacted_documents": "redacted_documents.jsonl",
    "entities": "entities.jsonl",
    "claims": "claims.jsonl",
    "claim_clusters": "claim_clusters.jsonl",
    "trust_scores": "trust_scores.jsonl",
    "claim_reviews": "claim_reviews.jsonl",
    "source_health": "source_health.jsonl",
    "retry_candidates": "retry_candidates.jsonl",
    "incremental_fetches": "incremental_fetches.jsonl",
    "crawl_run": "crawl_run.jsonl",
}

_BEARER = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class _AuthContext:
    """Authenticated caller details used by protected routes.

    Attributes:
        actor (str): Analyst or service-account label for audit events.
        authenticated (bool): Whether the request satisfied the configured auth
            boundary.
    """

    actor: str
    authenticated: bool


def create_app(
    output_root: str | Path | None = None,
    *,
    settings: DeploymentSettings | None = None,
) -> FastAPI:
    """Create the API app bound to configured run storage.

    Args:
        output_root (str | Path | None): Optional run storage root. Tests and
            local scripts pass this directly; deployments normally use
            ``CRAWLER_RUN_STORAGE_PATH``.
        settings (DeploymentSettings | None): Optional parsed deployment
            settings. When omitted, environment variables are read.

    Returns:
        FastAPI: Configured application instance.

    Raises:
        ValueError: Raised when deployment settings are invalid.
    """

    active_settings = settings or load_deployment_settings()
    if output_root is not None:
        active_settings = replace(active_settings, run_storage_path=Path(output_root))
    validate_deployment_settings(active_settings)
    root = active_settings.run_storage_path
    auth_dependency = _make_auth_dependency(active_settings)

    app = FastAPI(
        title="Webcrawler Intelligence API",
        version="0.1.0",
        description="API boundary over auditable crawler run artifacts.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(active_settings.cors_origins),
        allow_origin_regex=active_settings.cors_origin_regex,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Analyst-Id"],
    )

    @app.get("/")
    def index() -> dict[str, Any]:
        """Return a small API index for humans and integration tests.

        Returns:
            dict[str, Any]: API metadata and public deployment settings.
        """

        return {
            "service": "Webcrawler Intelligence API",
            "status": "ok",
            "docs": "/docs",
            "deployment": active_settings.public_dict(),
            "endpoints": [
                "/health",
                "/runs",
                "/runs/{run_id}/summary",
                "/runs/{run_id}/records/{record_name}",
                "/runs/{run_id}/map-data",
                "/runs/{run_id}/evidence-export",
                "/runs/{run_id}/claim-reviews",
                "/runs/{run_id}/map",
                "/audit-events",
            ],
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        """Return the public health probe used by deployment checks.

        Returns:
            dict[str, str]: Minimal health response.
        """

        return {"status": "ok"}

    @app.get("/runs")
    def list_runs(auth: _AuthContext = Depends(auth_dependency)) -> dict[str, Any]:
        """List crawler runs that have summary metadata.

        Args:
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.

        Returns:
            dict[str, Any]: Run summaries safe for the analyst UI.
        """

        runs = [
            {
                "run_id": summary.get("run_id"),
                "status": summary.get("status"),
                "started_at": summary.get("started_at"),
                "finished_at": summary.get("finished_at"),
                "sources_loaded": summary.get("sources_loaded", 0),
                "claims_extracted": summary.get("claims_extracted", 0),
            }
            for summary in _list_run_summaries(active_settings, root)
        ]
        return {"runs": runs}

    @app.get("/runs/{run_id}/summary")
    def run_summary(
        run_id: str,
        auth: _AuthContext = Depends(auth_dependency),
    ) -> dict[str, Any]:
        """Return the summary record for one crawler run.

        Args:
            run_id (str): Stable run identifier.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.

        Returns:
            dict[str, Any]: Stored ``run_summary.json`` payload.
        """

        return _run_summary_payload(active_settings, root, run_id)

    @app.get("/runs/{run_id}/records/{record_name}")
    def run_records(
        run_id: str,
        record_name: str,
        auth: _AuthContext = Depends(auth_dependency),
    ) -> dict[str, Any]:
        """Return one named JSONL record set for a crawler run.

        Args:
            run_id (str): Stable run identifier.
            record_name (str): Public record alias requested by the API caller.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.

        Returns:
            dict[str, Any]: Record alias and JSONL records.

        Raises:
            HTTPException: Raised when the record alias is not allowlisted.
        """

        filename = RECORD_ALLOWLIST.get(record_name)
        if filename is None:
            allowed = ", ".join(sorted(RECORD_ALLOWLIST))
            raise HTTPException(
                status_code=404,
                detail=f"unknown record type; allowed: {allowed}",
            )
        records = _run_record_payloads(active_settings, root, run_id, record_name, filename)
        return {"record_name": record_name, "records": records}

    @app.get("/runs/{run_id}/map-data")
    def map_data(
        run_id: str,
        auth: _AuthContext = Depends(auth_dependency),
        source_id: str | None = None,
        claim_type: str | None = None,
        min_trust: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
        include_demo_overlays: bool = False,
    ) -> dict[str, Any]:
        """Build API-backed map data for one crawler run.

        Args:
            run_id (str): Stable run identifier.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.
            source_id (str | None): Optional source filter.
            claim_type (str | None): Optional claim-type filter.
            min_trust (float | None): Optional minimum final trust score.
            include_demo_overlays (bool): Whether to include static demo
                overlays.

        Returns:
            dict[str, Any]: Shared map-data contract consumed by static and Next
            UIs.
        """

        return _map_data_payload(
            settings=active_settings,
            root=root,
            run_id=run_id,
            source_id=source_id,
            claim_type=claim_type,
            min_trust=min_trust,
            include_demo_overlays=include_demo_overlays,
        )

    @app.get("/runs/{run_id}/claim-reviews")
    def claim_reviews(
        run_id: str,
        auth: _AuthContext = Depends(auth_dependency),
        claim_id: str | None = None,
        latest_only: bool = True,
    ) -> dict[str, Any]:
        """Return analyst review decisions for one run.

        Args:
            run_id (str): Stable run identifier.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.
            claim_id (str | None): Optional claim filter.
            latest_only (bool): Whether to return only the latest decision per
                claim.

        Returns:
            dict[str, Any]: Review records separate from extracted claims.
        """

        reviews = _claim_reviews_for_run(active_settings, root, run_id)
        if claim_id:
            reviews = [review for review in reviews if review.claim_id == claim_id]
        if latest_only:
            reviews = list(latest_reviews_by_claim(reviews).values())
        reviews.sort(key=lambda review: (review.claim_id, review.reviewed_at))
        return {
            "run_id": run_id,
            "claim_id": claim_id,
            "latest_only": latest_only,
            "reviews": [review_to_public_dict(review) for review in reviews],
        }

    @app.post("/runs/{run_id}/claim-reviews")
    def save_claim_review(
        run_id: str,
        payload: dict[str, Any],
        request: Request,
        auth: _AuthContext = Depends(auth_dependency),
    ) -> dict[str, Any]:
        """Append one analyst claim-review decision and audit the action.

        Args:
            run_id (str): Stable run identifier.
            payload (dict[str, Any]): Review status, claim ID, and notes.
            request (Request): FastAPI request used to capture route path.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.

        Returns:
            dict[str, Any]: Saved review record and audit event ID.
        """

        records = _load_map_records(active_settings, root, run_id)
        claim_id = _text_or_none(payload.get("claim_id"))
        if claim_id is None:
            raise HTTPException(status_code=422, detail="claim_id is required")
        claim = next((item for item in records.claims if item.claim_id == claim_id), None)
        if claim is None:
            raise HTTPException(status_code=404, detail="claim not found")
        document_by_id = {
            document.document_id: document for document in records.documents
        }
        document = document_by_id.get(claim.document_id)
        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=422, detail="metadata must be an object")
        try:
            review = create_claim_review(
                run_id=run_id,
                claim_id=claim_id,
                review_status=str(payload.get("review_status", "")),
                reviewer=auth.actor,
                notes=str(payload.get("notes", "")),
                document_id=claim.document_id,
                source_id=document.source_id if document else None,
                metadata=metadata,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        _store_claim_review(active_settings, root, run_id, review)
        event = record_audit_event(
            active_settings.audit_log_path,
            event_type="claim_reviewed",
            actor=auth.actor,
            run_id=run_id,
            claim_id=claim_id,
            document_id=review.document_id,
            source_id=review.source_id,
            request_path=request.url.path,
            metadata={
                "review_id": review.review_id,
                "review_status": review.review_status,
                "notes_length": len(review.notes),
            },
        )
        _store_audit_event(active_settings, event)
        return {
            "audit_event_id": event.event_id,
            "review": review_to_public_dict(review),
        }

    @app.get("/runs/{run_id}/evidence-export")
    def evidence_export(
        run_id: str,
        request: Request,
        auth: _AuthContext = Depends(auth_dependency),
        claim_id: str | None = None,
        source_id: str | None = None,
        feature_id: str | None = None,
    ) -> dict[str, Any]:
        """Return an evidence packet and record a server-side audit event.

        Args:
            run_id (str): Stable run identifier.
            request (Request): FastAPI request used to capture the route path.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.
            claim_id (str | None): Optional claim filter for the export packet.
            source_id (str | None): Optional source filter for the export packet.
            feature_id (str | None): Optional map feature filter for zone or
                marker exports.

        Returns:
            dict[str, Any]: Evidence packet plus the audit event ID.
        """

        packet = _evidence_export_payload(
            settings=active_settings,
            root=root,
            run_id=run_id,
            claim_id=claim_id,
            source_id=source_id,
            feature_id=feature_id,
        )
        event = record_audit_event(
            active_settings.audit_log_path,
            event_type="evidence_exported",
            actor=auth.actor,
            run_id=run_id,
            claim_id=claim_id,
            source_id=source_id,
            request_path=request.url.path,
            metadata={
                "claim_count": len(packet["claims"]),
                "document_count": len(packet["documents"]),
                "source_count": len(packet["sources"]),
                "map_feature_count": len(packet["map_features"]),
                "feature_id": feature_id,
            },
        )
        _store_audit_event(active_settings, event)
        return {"audit_event_id": event.event_id, **packet}

    @app.post("/audit-events")
    def audit_events(
        payload: dict[str, Any],
        request: Request,
        auth: _AuthContext = Depends(auth_dependency),
    ) -> dict[str, Any]:
        """Record an analyst UI audit event.

        Args:
            payload (dict[str, Any]): JSON body with ``event_type`` and optional
                run, claim, document, source, and metadata fields.
            request (Request): FastAPI request used to capture the route path.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.

        Returns:
            dict[str, Any]: Serialized audit event.

        Raises:
            HTTPException: Raised when event data is invalid.
        """

        metadata = payload.get("metadata", {})
        if not isinstance(metadata, dict):
            raise HTTPException(status_code=422, detail="metadata must be an object")
        try:
            event = record_audit_event(
                active_settings.audit_log_path,
                event_type=str(payload.get("event_type", "")),
                actor=auth.actor,
                run_id=_text_or_none(payload.get("run_id")),
                claim_id=_text_or_none(payload.get("claim_id")),
                document_id=_text_or_none(payload.get("document_id")),
                source_id=_text_or_none(payload.get("source_id")),
                request_path=request.url.path,
                metadata=metadata,
            )
            _store_audit_event(active_settings, event)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        return {"event": event.to_dict()}

    @app.get("/runs/{run_id}/map", response_class=HTMLResponse)
    def run_map(
        run_id: str,
        auth: _AuthContext = Depends(auth_dependency),
    ) -> str:
        """Render the API-backed HTML map shell for one crawler run.

        Args:
            run_id (str): Stable run identifier.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.

        Returns:
            str: HTML map shell.
        """

        data = _map_data_payload(
            settings=active_settings,
            root=root,
            run_id=run_id,
            source_id=None,
            claim_type=None,
            min_trust=None,
            include_demo_overlays=False,
        )
        return render_map_html(data, api_base_url="", run_id=run_id)

    return app

def _make_auth_dependency(settings: DeploymentSettings):
    """Create a FastAPI dependency for the configured auth boundary.

    Args:
        settings (DeploymentSettings): Deployment settings that decide whether
            auth is required and which token is valid.

    Returns:
        Callable[..., _AuthContext]: Dependency function used by protected
        routes.
    """

    def dependency(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(_BEARER),
        ],
        analyst_id: Annotated[str | None, Header(alias="X-Analyst-Id")] = None,
    ) -> _AuthContext:
        """Authenticate one protected request.

        Args:
            credentials (HTTPAuthorizationCredentials | None): Parsed bearer
                credentials from FastAPI.
            analyst_id (str | None): Optional analyst label for audit events.

        Returns:
            _AuthContext: Authenticated caller context.

        Raises:
            HTTPException: Raised when auth is required and the token is missing
                or invalid.
        """

        actor = _actor_from_header(analyst_id)
        if not settings.auth_required:
            return _AuthContext(actor=actor, authenticated=False)
        if credentials is None:
            _raise_auth_error("missing API bearer token")
        expected = settings.api_token or ""
        if not secrets.compare_digest(credentials.credentials, expected):
            _raise_auth_error("invalid API bearer token")
        return _AuthContext(actor=actor, authenticated=True)

    return dependency


def _raise_auth_error(detail: str) -> None:
    """Raise a bearer-token authentication error.

    Args:
        detail (str): Client-safe error detail.

    Raises:
        HTTPException: Always raised with ``401`` status.
    """

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


def _actor_from_header(value: str | None) -> str:
    """Return an audit actor label from a request header.

    Args:
        value (str | None): Optional ``X-Analyst-Id`` header.

    Returns:
        str: Non-empty actor label.
    """

    actor = (value or "authenticated-analyst").strip()
    return actor[:120] or "authenticated-analyst"


def _run_dir(root: Path, run_id: str) -> Path:
    """Return the validated directory for one run.

    Args:
        root (Path): Root directory containing run outputs.
        run_id (str): Stable run identifier.

    Returns:
        Path: Directory for the requested run.

    Raises:
        HTTPException: Raised when the run ID is unsafe or missing.
    """

    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail="run not found")
    run_dir = root / run_id
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=404, detail="run not found")
    return run_dir


def _read_json(path: Path) -> dict[str, Any]:
    """Read a JSON artifact from disk.

    Args:
        path (Path): JSON file path.

    Returns:
        dict[str, Any]: Parsed JSON object.

    Raises:
        HTTPException: Raised when the artifact is missing or invalid.
    """

    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not found")
    try:
        import json

        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise HTTPException(status_code=500, detail=f"invalid JSON: {path}") from error


def _using_sqlite(settings: DeploymentSettings) -> bool:
    """Return whether the API should read durable SQLite storage."""

    return settings.storage_backend == "sqlite"


def _list_run_summaries(
    settings: DeploymentSettings,
    root: Path,
) -> list[dict[str, Any]]:
    """List run summaries from the configured storage backend."""

    if _using_sqlite(settings):
        connection = initialize_sqlite(settings.run_db_path)
        try:
            return list_run_summaries(connection)
        finally:
            connection.close()
    runs = []
    if root.exists():
        for run_dir in sorted(root.iterdir()):
            if not run_dir.is_dir():
                continue
            summary_path = run_dir / "run_summary.json"
            if summary_path.exists():
                runs.append(_read_json(summary_path))
    return runs


def _run_summary_payload(
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
) -> dict[str, Any]:
    """Fetch one run summary from the configured storage backend."""

    if _using_sqlite(settings):
        _validate_run_id(run_id)
        connection = initialize_sqlite(settings.run_db_path)
        try:
            summary = fetch_run_summary(connection, run_id)
        finally:
            connection.close()
        if summary is None:
            raise HTTPException(status_code=404, detail="run not found")
        return summary
    return _read_json(_run_dir(root, run_id) / "run_summary.json")


def _run_record_payloads(
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
    record_name: str,
    filename: str,
) -> list[dict[str, Any]]:
    """Fetch one run record set from the configured storage backend."""

    if _using_sqlite(settings):
        _validate_run_id(run_id)
        connection = initialize_sqlite(settings.run_db_path)
        try:
            if fetch_run_summary(connection, run_id) is None:
                raise HTTPException(status_code=404, detail="run not found")
            return fetch_run_records(
                connection,
                run_id=run_id,
                record_name=record_name,
            )
        finally:
            connection.close()
    records_path = _run_dir(root, run_id) / "records" / filename
    if not records_path.exists():
        return []
    return read_jsonl(records_path)


def _load_map_records(
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
) -> MapUiRecords:
    """Load map records from JSONL or SQLite storage."""

    if not _using_sqlite(settings):
        return load_map_records(_run_dir(root, run_id) / "records")
    _validate_run_id(run_id)
    connection = initialize_sqlite(settings.run_db_path)
    try:
        if fetch_run_summary(connection, run_id) is None:
            raise HTTPException(status_code=404, detail="run not found")
        return MapUiRecords(
            sources=_records_as_models(
                fetch_run_records(connection, run_id=run_id, record_name="sources"),
                Source,
            ),
            claims=_records_as_models(
                fetch_run_records(connection, run_id=run_id, record_name="claims"),
                Claim,
            ),
            trust_scores=_records_as_models(
                fetch_run_records(
                    connection,
                    run_id=run_id,
                    record_name="trust_scores",
                ),
                TrustScore,
            ),
            documents=_records_as_models(
                fetch_run_records(
                    connection,
                    run_id=run_id,
                    record_name="fetched_documents",
                ),
                FetchedDocument,
            ),
            claim_reviews=_records_as_models(
                fetch_run_records(
                    connection,
                    run_id=run_id,
                    record_name="claim_reviews",
                ),
                ClaimReview,
            ),
        )
    finally:
        connection.close()


def _records_as_models(records: list[dict[str, Any]], record_type):
    """Convert stored payloads to dataclass records."""

    return [record_type(**record) for record in records]


def _claim_reviews_for_run(
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
) -> list[ClaimReview]:
    """Load claim reviews from the configured storage backend."""

    if _using_sqlite(settings):
        return _load_map_records(settings, root, run_id).claim_reviews
    return read_claim_reviews(_run_dir(root, run_id) / "records" / "claim_reviews.jsonl")


def _store_claim_review(
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
    review: ClaimReview,
) -> None:
    """Persist one review in the configured storage backend."""

    if _using_sqlite(settings):
        connection = initialize_sqlite(settings.run_db_path)
        try:
            upsert_run_records(
                connection,
                run_id=run_id,
                record_name="claim_reviews",
                records=[review],
            )
        finally:
            connection.close()
        return
    append_claim_review(_run_dir(root, run_id) / "records" / "claim_reviews.jsonl", review)


def _store_audit_event(settings: DeploymentSettings, event) -> None:
    """Mirror audit events into durable storage when SQLite mode is active."""

    if not _using_sqlite(settings):
        return
    connection = initialize_sqlite(settings.run_db_path)
    try:
        upsert_audit_event(connection, event)
    finally:
        connection.close()


def _validate_run_id(run_id: str) -> None:
    """Reject unsafe run IDs before database lookup."""

    if "/" in run_id or "\\" in run_id or run_id in {"", ".", ".."}:
        raise HTTPException(status_code=404, detail="run not found")


def _map_data_payload(
    *,
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
    source_id: str | None,
    claim_type: str | None,
    min_trust: float | None,
    include_demo_overlays: bool,
) -> dict[str, Any]:
    """Build a map-data response from stored run records.

    Args:
        root (Path): Root directory containing run outputs.
        run_id (str): Stable run identifier.
        source_id (str | None): Optional source filter.
        claim_type (str | None): Optional claim-type filter.
        min_trust (float | None): Optional minimum final trust score.
        include_demo_overlays (bool): Whether to include static demo overlays.

    Returns:
        dict[str, Any]: Map-data payload.
    """

    records = _load_map_records(settings, root, run_id)
    sources, documents, claims, trust_scores, claim_reviews = _filter_map_records(
        sources=records.sources,
        documents=records.documents,
        claims=records.claims,
        trust_scores=records.trust_scores,
        claim_reviews=records.claim_reviews,
        source_id=source_id,
        claim_type=claim_type,
        min_trust=min_trust,
    )
    return build_map_data(
        sources=sources,
        documents=documents,
        claims=claims,
        trust_scores=trust_scores,
        claim_reviews=claim_reviews,
        include_demo_overlays=include_demo_overlays,
    )


def _evidence_export_payload(
    *,
    settings: DeploymentSettings,
    root: Path,
    run_id: str,
    claim_id: str | None,
    source_id: str | None,
    feature_id: str | None,
) -> dict[str, Any]:
    """Build an analyst evidence export packet from run records.

    Args:
        root (Path): Root directory containing run outputs.
        run_id (str): Stable run identifier.
        claim_id (str | None): Optional claim filter.
        source_id (str | None): Optional source filter.
        feature_id (str | None): Optional map feature filter.

    Returns:
        dict[str, Any]: JSON-safe evidence export packet.

    Raises:
        HTTPException: Raised when a requested claim does not exist.
    """

    records = _load_map_records(settings, root, run_id)
    claims = records.claims
    if claim_id is not None:
        claims = [claim for claim in claims if claim.claim_id == claim_id]
        if not claims:
            raise HTTPException(status_code=404, detail="claim not found")

    documents_by_id = {document.document_id: document for document in records.documents}
    if source_id is not None:
        claims = [
            claim
            for claim in claims
            if documents_by_id.get(claim.document_id) is not None
            and documents_by_id[claim.document_id].source_id == source_id
        ]

    claim_ids = {claim.claim_id for claim in claims}
    document_ids = {claim.document_id for claim in claims}
    documents = [
        document for document in records.documents if document.document_id in document_ids
    ]
    source_ids = {document.source_id for document in documents}
    if source_id is not None:
        source_ids.add(source_id)
    sources = [source for source in records.sources if source.source_id in source_ids]
    trust_scores = [
        score for score in records.trust_scores if score.claim_id in claim_ids
    ]
    reviews = [
        review for review in records.claim_reviews if review.claim_id in claim_ids
    ]
    latest_reviews = latest_reviews_by_claim(reviews)
    map_data = build_map_data(
        sources=records.sources,
        documents=records.documents,
        claims=records.claims,
        trust_scores=records.trust_scores,
        claim_reviews=records.claim_reviews,
        include_demo_overlays=True,
    )
    map_features = map_data["features"]["features"]
    if feature_id is not None:
        map_features = [
            feature
            for feature in map_features
            if feature.get("properties", {}).get("id") == feature_id
        ]
        if not map_features:
            raise HTTPException(status_code=404, detail="map feature not found")
        feature_claim_ids = {
            str(feature.get("properties", {}).get("claim_id"))
            for feature in map_features
            if feature.get("properties", {}).get("claim_id")
        }
        if feature_claim_ids and claim_id is None:
            claims = [claim for claim in records.claims if claim.claim_id in feature_claim_ids]
            claim_ids = {claim.claim_id for claim in claims}
            document_ids = {claim.document_id for claim in claims}
            documents = [
                document
                for document in records.documents
                if document.document_id in document_ids
            ]
            source_ids = {document.source_id for document in documents}
            sources = [
                source for source in records.sources if source.source_id in source_ids
            ]
            trust_scores = [
                score for score in records.trust_scores if score.claim_id in claim_ids
            ]
            reviews = [
                review
                for review in records.claim_reviews
                if review.claim_id in claim_ids
            ]
            latest_reviews = latest_reviews_by_claim(reviews)

    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "claim_filter": claim_id,
        "source_filter": source_id,
        "feature_filter": feature_id,
        "claims": [claim.to_dict() for claim in claims],
        "documents": [document.to_dict() for document in documents],
        "sources": [source.to_dict() for source in sources],
        "trust_scores": [score.to_dict() for score in trust_scores],
        "review_notes": [
            review_to_public_dict(review)
            for review in latest_reviews.values()
        ],
        "review_history": [review_to_public_dict(review) for review in reviews],
        "map_features": map_features,
    }


def _text_or_none(value: Any) -> str | None:
    """Convert optional JSON values to strings for audit records.

    Args:
        value (Any): Value supplied by a JSON request body.

    Returns:
        str | None: Trimmed text or ``None``.
    """

    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _filter_map_records(
    *,
    sources,
    documents,
    claims,
    trust_scores,
    claim_reviews,
    source_id: str | None,
    claim_type: str | None,
    min_trust: float | None,
):
    """Filter map records before building map data.

    Args:
        sources (Any): Source records.
        documents (Any): Document records.
        claims (Any): Claim records.
        trust_scores (Any): Trust score records.
        claim_reviews (Any): Analyst review records.
        source_id (str | None): Optional source filter.
        claim_type (str | None): Optional claim-type filter.
        min_trust (float | None): Optional minimum final trust score.

    Returns:
        tuple[Any, Any, Any, Any, Any]: Filtered sources, documents, claims,
        trust scores, and claim reviews.
    """

    trust_by_claim = {score.claim_id: score for score in trust_scores}
    documents_by_id = {document.document_id: document for document in documents}

    filtered_claims = []
    for claim in claims:
        document = documents_by_id.get(claim.document_id)
        if source_id and (document is None or document.source_id != source_id):
            continue
        if claim_type and claim.claim_type != claim_type:
            continue
        score = trust_by_claim.get(claim.claim_id)
        if min_trust is not None:
            final_score = score.final_score if score else None
            if final_score is None or final_score < min_trust:
                continue
        filtered_claims.append(claim)

    claim_ids = {claim.claim_id for claim in filtered_claims}
    document_ids = {claim.document_id for claim in filtered_claims}
    filtered_trust = [score for score in trust_scores if score.claim_id in claim_ids]
    filtered_reviews = [
        review for review in claim_reviews if review.claim_id in claim_ids
    ]
    filtered_documents = [
        document for document in documents if document.document_id in document_ids
    ]
    if source_id:
        filtered_sources = [source for source in sources if source.source_id == source_id]
    else:
        source_ids = {document.source_id for document in filtered_documents}
        filtered_sources = [
            source for source in sources if not source_ids or source.source_id in source_ids
        ]
    return (
        filtered_sources,
        filtered_documents,
        filtered_claims,
        filtered_trust,
        filtered_reviews,
    )


app = create_app()
