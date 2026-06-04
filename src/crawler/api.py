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
from crawler.map_ui import build_map_data, load_map_records, render_map_html
from crawler.storage import read_jsonl


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

        runs = []
        if root.exists():
            for run_dir in sorted(root.iterdir()):
                if not run_dir.is_dir():
                    continue
                summary_path = run_dir / "run_summary.json"
                if not summary_path.exists():
                    continue
                summary = _read_json(summary_path)
                runs.append(
                    {
                        "run_id": summary.get("run_id", run_dir.name),
                        "status": summary.get("status"),
                        "started_at": summary.get("started_at"),
                        "finished_at": summary.get("finished_at"),
                        "sources_loaded": summary.get("sources_loaded", 0),
                        "claims_extracted": summary.get("claims_extracted", 0),
                    }
                )
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

        return _read_json(_run_dir(root, run_id) / "run_summary.json")

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
        records_path = _run_dir(root, run_id) / "records" / filename
        if not records_path.exists():
            return {"record_name": record_name, "records": []}
        return {"record_name": record_name, "records": read_jsonl(records_path)}

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
            root=root,
            run_id=run_id,
            source_id=source_id,
            claim_type=claim_type,
            min_trust=min_trust,
            include_demo_overlays=include_demo_overlays,
        )

    @app.get("/runs/{run_id}/evidence-export")
    def evidence_export(
        run_id: str,
        request: Request,
        auth: _AuthContext = Depends(auth_dependency),
        claim_id: str | None = None,
    ) -> dict[str, Any]:
        """Return an evidence packet and record a server-side audit event.

        Args:
            run_id (str): Stable run identifier.
            request (Request): FastAPI request used to capture the route path.
            auth (_AuthContext): Authenticated request context supplied by the
                API dependency.
            claim_id (str | None): Optional claim filter for the export packet.

        Returns:
            dict[str, Any]: Evidence packet plus the audit event ID.
        """

        packet = _evidence_export_payload(root=root, run_id=run_id, claim_id=claim_id)
        event = record_audit_event(
            active_settings.audit_log_path,
            event_type="evidence_exported",
            actor=auth.actor,
            run_id=run_id,
            claim_id=claim_id,
            request_path=request.url.path,
            metadata={
                "claim_count": len(packet["claims"]),
                "document_count": len(packet["documents"]),
                "source_count": len(packet["sources"]),
            },
        )
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


def _map_data_payload(
    *,
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

    records_dir = _run_dir(root, run_id) / "records"
    records = load_map_records(records_dir)
    sources, documents, claims, trust_scores = _filter_map_records(
        sources=records.sources,
        documents=records.documents,
        claims=records.claims,
        trust_scores=records.trust_scores,
        source_id=source_id,
        claim_type=claim_type,
        min_trust=min_trust,
    )
    return build_map_data(
        sources=sources,
        documents=documents,
        claims=claims,
        trust_scores=trust_scores,
        include_demo_overlays=include_demo_overlays,
    )


def _evidence_export_payload(
    *,
    root: Path,
    run_id: str,
    claim_id: str | None,
) -> dict[str, Any]:
    """Build an analyst evidence export packet from run records.

    Args:
        root (Path): Root directory containing run outputs.
        run_id (str): Stable run identifier.
        claim_id (str | None): Optional claim filter.

    Returns:
        dict[str, Any]: JSON-safe evidence export packet.

    Raises:
        HTTPException: Raised when a requested claim does not exist.
    """

    records = load_map_records(_run_dir(root, run_id) / "records")
    claims = records.claims
    if claim_id is not None:
        claims = [claim for claim in claims if claim.claim_id == claim_id]
        if not claims:
            raise HTTPException(status_code=404, detail="claim not found")

    claim_ids = {claim.claim_id for claim in claims}
    document_ids = {claim.document_id for claim in claims}
    documents = [
        document for document in records.documents if document.document_id in document_ids
    ]
    source_ids = {document.source_id for document in documents}
    sources = [source for source in records.sources if source.source_id in source_ids]
    trust_scores = [
        score for score in records.trust_scores if score.claim_id in claim_ids
    ]

    return {
        "run_id": run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "claim_filter": claim_id,
        "claims": [claim.to_dict() for claim in claims],
        "documents": [document.to_dict() for document in documents],
        "sources": [source.to_dict() for source in sources],
        "trust_scores": [score.to_dict() for score in trust_scores],
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
        source_id (str | None): Optional source filter.
        claim_type (str | None): Optional claim-type filter.
        min_trust (float | None): Optional minimum final trust score.

    Returns:
        tuple[Any, Any, Any, Any]: Filtered sources, documents, claims, and
        trust scores.
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
    return filtered_sources, filtered_documents, filtered_claims, filtered_trust


app = create_app()
