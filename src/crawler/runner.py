"""Pipeline orchestration for repeatable local and demo runs.

The runner connects the individual modules into named stages. It writes summary,
record, UI, and log artifacts under one run directory so a developer can rerun a
bounded crawl and inspect each output without relying on hidden process state.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.request import Request, build_opener

from crawler.clean import clean_documents, cleaning_log_entry
from crawler.corroboration import (
    annotate_claims_with_clusters,
    cluster_claims,
    corroboration_log_entry,
)
from crawler.discovery import discover_expanded_source_urls, discover_manual_seed_urls
from crawler.extract import extract_documents, extraction_log_entry
from crawler.fetch import fetch_items, fetch_log_entry
from crawler.incremental import (
    changed_document_ids,
    classify_incremental_fetches,
    incremental_log_entry,
    incremental_summary,
    load_previous_documents,
)
from crawler.map_ui import map_ui_log_entry, write_map_ui
from crawler.models import AccessDecision, CrawlRun, IncrementalFetch, Source
from crawler.redact import redact_documents, redaction_log_entry
from crawler.robots import FetchPolicy, access_log_entry, evaluate_access, make_headers
from crawler.robots import robots_url as source_robots_url
from crawler.signals import extract_signal_batch, signal_log_entry
from crawler.source_health import (
    assess_source_health,
    frontier_log_entry,
    source_health_log_entry,
)
from crawler.source_registry import load_source_registry
from crawler.storage import append_jsonl, storage_log_entry
from crawler.trust import score_claims, trust_log_entry


DEFAULT_STAGES = ["validate_sources", "discover_items"]
AUTOMATIC_CRAWL_STAGES = [
    "validate_sources",
    "expand_discovery",
    "discover_items",
    "check_access",
    "fetch_documents",
    "extract_documents",
    "clean_documents",
    "redact_documents",
    "extract_signals",
    "score_trust",
    "assess_source_health",
    "build_map_ui",
]
INCREMENTAL_CRAWL_STAGES = [
    "validate_sources",
    "expand_discovery",
    "discover_items",
    "check_access",
    "fetch_documents",
    "classify_incremental_fetches",
    "extract_documents",
    "clean_documents",
    "redact_documents",
    "extract_signals",
    "detect_corroboration",
    "score_trust",
    "assess_source_health",
    "build_map_ui",
]


@dataclass(slots=True)
class RunResult:
    """Summarize the files and counters produced by one pipeline run.
    
    These lightweight classes make pipeline artifacts explicit. That helps analysts and
    developers trace where each field came from instead of passing anonymous
    dictionaries through the system.
    
    Attributes:
        run (CrawlRun): Stored value named ``run`` that travels with this record.
        summary (dict[str, Any]): Stored value named ``summary`` that travels with this
            record.
        output_dir (Path): Stored value named ``output_dir`` that travels with this
            record.
    """
    run: CrawlRun
    summary: dict[str, Any]
    output_dir: Path


def run_pipeline(
    *,
    source_registry_path: str | Path = "data/sources.csv",
    output_root: str | Path = "outputs/runs",
    run_id: str | None = None,
    enabled_stages: list[str] | None = None,
    max_sources: int | None = None,
    max_items_per_source: int | None = None,
    max_fetches: int | None = None,
    policy: FetchPolicy = FetchPolicy(),
    opener: Any | None = None,
    robots_text_provider: Callable[[Source, FetchPolicy], str | None] | None = None,
    map_api_base_url: str | None = None,
    previous_run_id: str | None = None,
) -> RunResult:
    """Run a configured subset of local, network-free pipeline stages."""
    started_at = datetime.now(UTC).isoformat()
    actual_run_id = run_id or _default_run_id()
    stages = _expand_stages(enabled_stages or list(DEFAULT_STAGES))
    output_dir = Path(output_root) / actual_run_id
    records_dir = output_dir / "records"
    logs_dir = output_dir / "logs"
    output_dir.mkdir(parents=True, exist_ok=True)
    records_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "run_events.jsonl"

    run = CrawlRun(
        run_id=actual_run_id,
        started_at=started_at,
        status="running",
        enabled_stages=stages,
        max_sources=max_sources,
        max_items_per_source=max_items_per_source,
        max_fetches=max_fetches,
        output_dir=str(output_dir),
    )
    errors: list[dict[str, Any]] = []
    sources: list[Source] = []
    items = []
    decisions: list[AccessDecision] = []
    fetched_documents = []
    extracted_documents = []
    clean_records = []
    redacted_records = []
    entities = []
    claims = []
    claim_clusters = []
    trust_scores = []
    source_health_records = []
    retry_candidates = []
    incremental_records: list[IncrementalFetch] = []
    actual_previous_run_id = None
    previous_documents = {}

    try:
        if _stage_enabled(stages, "classify_incremental_fetches"):
            actual_previous_run_id, previous_documents = load_previous_documents(
                output_root,
                current_run_id=actual_run_id,
                previous_run_id=previous_run_id,
            )
            _write_log(
                log_path,
                {
                    "stage": "load_previous_run_metadata",
                    "previous_run_id": actual_previous_run_id,
                    "previous_document_keys": len(previous_documents),
                },
            )

        if _needs_sources(stages):
            registry = load_source_registry(source_registry_path)
            sources = registry.sources[:max_sources] if max_sources else registry.sources
            _write_log(
                log_path,
                {
                    "stage": "validate_sources",
                    "sources_loaded": len(sources),
                    "sources_skipped": len(registry.skipped),
                },
            )
            append_jsonl(records_dir / "sources.jsonl", sources)

        if _needs_discovery(stages):
            if _stage_enabled(stages, "expand_discovery"):
                items = discover_expanded_source_urls(
                    sources,
                    policy=policy,
                    opener=opener,
                )
            else:
                items = discover_manual_seed_urls(sources)
            if max_items_per_source is not None:
                items = _limit_items_per_source(items, max_items_per_source)
            _write_log(
                log_path,
                {
                    "stage": "discover_items",
                    "items_discovered": len(items),
                },
            )
            append_jsonl(records_dir / "discovered_items.jsonl", items)
            _write_log(
                log_path,
                storage_log_entry(
                    destination=str(records_dir / "discovered_items.jsonl"),
                    record_count=len(items),
                    storage_type="jsonl",
                ),
            )

        if _stage_enabled(stages, "check_access"):
            decisions = _check_access(
                items,
                sources,
                policy=policy,
                robots_text_provider=robots_text_provider,
            )
            append_jsonl(records_dir / "access_decisions.jsonl", decisions)
            for decision in decisions:
                _write_log(log_path, access_log_entry(decision))

        if _stage_enabled(stages, "fetch_documents"):
            allowed_pairs = [
                (item, decision)
                for item, decision in zip(items, decisions, strict=False)
                if decision.allowed
            ]
            if max_fetches is not None:
                allowed_pairs = allowed_pairs[:max_fetches]
            fetched_documents = fetch_items(
                allowed_pairs,
                cache_dir=output_dir / "raw_cache",
                policy=policy,
                opener=opener,
                previous_documents=previous_documents or None,
            )
            append_jsonl(records_dir / "fetched_documents.jsonl", fetched_documents)
            for document in fetched_documents:
                _write_log(log_path, fetch_log_entry(document))

        if _stage_enabled(stages, "classify_incremental_fetches"):
            incremental_records = classify_incremental_fetches(
                run_id=actual_run_id,
                documents=fetched_documents,
                previous_documents=previous_documents,
                previous_run_id=actual_previous_run_id,
            )
            append_jsonl(records_dir / "incremental_fetches.jsonl", incremental_records)
            _write_log(log_path, incremental_log_entry(incremental_records))

        if _stage_enabled(stages, "extract_documents"):
            documents_for_extraction = _documents_for_extraction(
                fetched_documents,
                incremental_records,
            )
            extracted_documents = extract_documents(documents_for_extraction)
            append_jsonl(records_dir / "extracted_documents.jsonl", extracted_documents)
            for document in extracted_documents:
                _write_log(log_path, extraction_log_entry(document))

        if _stage_enabled(stages, "clean_documents"):
            clean_records = clean_documents(extracted_documents)
            append_jsonl(records_dir / "clean_documents.jsonl", clean_records)
            for document in clean_records:
                _write_log(log_path, cleaning_log_entry(document))

        if _stage_enabled(stages, "redact_documents"):
            redacted_records = redact_documents(clean_records)
            append_jsonl(records_dir / "redacted_documents.jsonl", redacted_records)
            for document in redacted_records:
                _write_log(log_path, redaction_log_entry(document))

        if _stage_enabled(stages, "extract_signals"):
            signal_extractions = extract_signal_batch(redacted_records)
            for extraction in signal_extractions:
                entities.extend(extraction.entities)
                claims.extend(extraction.claims)
                _write_log(log_path, signal_log_entry(extraction))
            append_jsonl(records_dir / "entities.jsonl", entities)

        if _stage_enabled(stages, "detect_corroboration"):
            claim_clusters = cluster_claims(
                claims,
                documents_by_id={
                    document.document_id: document for document in fetched_documents
                },
                sources_by_id={source.source_id: source for source in sources},
            )
            annotate_claims_with_clusters(claims, claim_clusters)
            append_jsonl(records_dir / "claim_clusters.jsonl", claim_clusters)
            _write_log(log_path, corroboration_log_entry(claim_clusters))

        if _stage_enabled(stages, "extract_signals"):
            append_jsonl(records_dir / "claims.jsonl", claims)

        if _stage_enabled(stages, "score_trust"):
            trust_scores = score_claims(
                claims,
                sources_by_claim_id=_sources_by_claim_id(claims, fetched_documents, sources),
                claim_clusters=claim_clusters,
            )
            append_jsonl(records_dir / "trust_scores.jsonl", trust_scores)
            for score in trust_scores:
                _write_log(log_path, trust_log_entry(score))

        if _stage_enabled(stages, "assess_source_health"):
            source_health_records, retry_candidates = assess_source_health(
                run_id=actual_run_id,
                sources=sources,
                discovered_items=items,
                access_decisions=decisions,
                fetched_documents=fetched_documents,
                extracted_documents=extracted_documents,
                claims=claims,
            )
            append_jsonl(records_dir / "source_health.jsonl", source_health_records)
            append_jsonl(records_dir / "retry_candidates.jsonl", retry_candidates)
            for health in source_health_records:
                _write_log(log_path, source_health_log_entry(health))
            _write_log(log_path, frontier_log_entry(retry_candidates))

        if "build_map_ui" in stages:
            ui_result = write_map_ui(
                output_dir / "ui" / "azerbaijan_energy_map.html",
                records_dir=records_dir,
                sources=sources,
                api_base_url=map_api_base_url,
                run_id=actual_run_id if map_api_base_url is not None else None,
            )
            _write_log(log_path, map_ui_log_entry(ui_result))
    except Exception as error:  # keep run summaries visible for config/schema failures
        errors.append(
            {
                "stage": "run_pipeline",
                "error_type": type(error).__name__,
                "message": str(error),
                "retryable": False,
                "created_at": datetime.now(UTC).isoformat(),
            },
        )

    run.finished_at = datetime.now(UTC).isoformat()
    run.errors = errors
    run.status = "failed" if errors else "success"
    summary = {
        "run_id": run.run_id,
        "started_at": run.started_at,
        "finished_at": run.finished_at,
        "status": run.status,
        "enabled_stages": run.enabled_stages,
        "sources_loaded": len(sources),
        "items_discovered": len(items),
        "access_decisions": len(decisions),
        "documents_fetched": len(fetched_documents),
        "documents_extracted": len(extracted_documents),
        "documents_cleaned": len(clean_records),
        "documents_redacted": len(redacted_records),
        "entities_extracted": len(entities),
        "claims_extracted": len(claims),
        "claim_clusters": len(claim_clusters),
        "trust_scores_created": len(trust_scores),
        "source_health_records": len(source_health_records),
        "retry_candidates": len(retry_candidates),
        "previous_run_id": actual_previous_run_id,
        "incremental_fetches": len(incremental_records),
        "incremental_summary": incremental_summary(incremental_records),
        "errors": errors,
        "outputs": [
            str(records_dir / "sources.jsonl"),
            str(records_dir / "discovered_items.jsonl"),
            str(records_dir / "access_decisions.jsonl"),
            str(records_dir / "fetched_documents.jsonl"),
            str(records_dir / "extracted_documents.jsonl"),
            str(records_dir / "clean_documents.jsonl"),
            str(records_dir / "redacted_documents.jsonl"),
            str(records_dir / "entities.jsonl"),
            str(records_dir / "claims.jsonl"),
            str(records_dir / "claim_clusters.jsonl"),
            str(records_dir / "trust_scores.jsonl"),
            str(records_dir / "source_health.jsonl"),
            str(records_dir / "retry_candidates.jsonl"),
            str(records_dir / "incremental_fetches.jsonl"),
            str(output_dir / "ui" / "azerbaijan_energy_map.html"),
            str(log_path),
        ],
    }
    (output_dir / "run_summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    append_jsonl(records_dir / "crawl_run.jsonl", [run])
    return RunResult(run=run, summary=summary, output_dir=output_dir)


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
    parser = argparse.ArgumentParser(description="Run local webcrawler stages.")
    parser.add_argument("--source-registry", default="data/sources.csv")
    parser.add_argument("--output-root", default="outputs/runs")
    parser.add_argument("--run-id")
    parser.add_argument(
        "--stages",
        default=",".join(DEFAULT_STAGES),
        help=(
            "Comma-separated stages. Supported: "
            "validate_sources,discover_items,check_access,fetch_documents,"
            "extract_documents,clean_documents,redact_documents,extract_signals,"
            "detect_corroboration,score_trust,assess_source_health,build_map_ui,expand_discovery,"
            "automatic_crawl,incremental_crawl,scheduled_crawl"
        ),
    )
    parser.add_argument("--max-sources", type=int)
    parser.add_argument("--max-items-per-source", type=int)
    parser.add_argument("--max-fetches", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--user-agent", default="webcrawler/0.1")
    parser.add_argument(
        "--map-api-base-url",
        help="Optional API base URL for generated HTML map refreshes.",
    )
    parser.add_argument(
        "--previous-run-id",
        help="Previous run ID for incremental or scheduled crawls.",
    )
    args = parser.parse_args(argv)

    result = run_pipeline(
        source_registry_path=args.source_registry,
        output_root=args.output_root,
        run_id=args.run_id,
        enabled_stages=[stage.strip() for stage in args.stages.split(",") if stage.strip()],
        max_sources=args.max_sources,
        max_items_per_source=args.max_items_per_source,
        max_fetches=args.max_fetches,
        policy=FetchPolicy(
            user_agent=args.user_agent,
            timeout_seconds=args.timeout_seconds,
        ),
        map_api_base_url=args.map_api_base_url,
        previous_run_id=args.previous_run_id,
    )
    print(result.output_dir)
    print(result.summary["status"])
    return 0 if result.summary["status"] == "success" else 1


def _limit_items_per_source(items, limit: int):
    """Support the module's public workflow by computing limit items per source.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        items (Any): Discovered crawl items being limited, checked, fetched, or
            converted.
        limit (int): Maximum number of records to keep for this bounded operation.
    
    Returns:
        Any: Result produced for the next pipeline step or caller.
    """
    counts: dict[str, int] = {}
    limited = []
    for item in items:
        count = counts.get(item.source_id, 0)
        if count >= limit:
            continue
        limited.append(item)
        counts[item.source_id] = count + 1
    return limited


def _write_log(path: Path, entry: dict[str, Any]) -> None:
    """Support the module's public workflow by computing write log.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        path (Path): Filesystem path used by this step. It may be a string or a ``Path``
            depending on the caller.
        entry (dict[str, Any]): Value named ``entry`` supplied by the caller for this
            pipeline step.
    
    Returns:
        None: This function is used for its side effect and does not return a value.
    """
    entry = {"created_at": datetime.now(UTC).isoformat(), **entry}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True))
        handle.write("\n")


def _default_run_id() -> str:
    """Support the module's public workflow by computing default run id.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Returns:
        str: String value ready for display, storage, or downstream parsing.
    """
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _expand_stages(stages: list[str]) -> list[str]:
    """Support the module's public workflow by computing expand stages.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        stages (list[str]): Pipeline stage names requested by the caller.
    
    Returns:
        list[str]: Result produced for the next pipeline step or caller.
    """
    expanded: list[str] = []
    for stage in stages:
        if stage == "automatic_crawl":
            expanded.extend(AUTOMATIC_CRAWL_STAGES)
        elif stage in {"incremental_crawl", "scheduled_crawl"}:
            expanded.extend(INCREMENTAL_CRAWL_STAGES)
        else:
            expanded.append(stage)
    return list(dict.fromkeys(expanded))


def _needs_sources(stages: list[str]) -> bool:
    """Support the module's public workflow by computing needs sources.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        stages (list[str]): Pipeline stage names requested by the caller.
    
    Returns:
        bool: Boolean decision used by the caller to choose the next pipeline step.
    """
    return any(
        stage in stages
        for stage in [
            "validate_sources",
            "expand_discovery",
            "discover_items",
            "check_access",
            "fetch_documents",
            "classify_incremental_fetches",
            "extract_documents",
            "clean_documents",
            "redact_documents",
            "extract_signals",
            "detect_corroboration",
            "score_trust",
            "assess_source_health",
            "build_map_ui",
        ]
    )


def _needs_discovery(stages: list[str]) -> bool:
    """Support the module's public workflow by computing needs discovery.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        stages (list[str]): Pipeline stage names requested by the caller.
    
    Returns:
        bool: Boolean decision used by the caller to choose the next pipeline step.
    """
    return any(
        stage in stages
        for stage in [
            "expand_discovery",
            "discover_items",
            "check_access",
            "fetch_documents",
            "classify_incremental_fetches",
            "extract_documents",
            "clean_documents",
            "redact_documents",
            "extract_signals",
            "detect_corroboration",
            "score_trust",
            "assess_source_health",
        ]
    )


def _stage_enabled(stages: list[str], stage: str) -> bool:
    """Support the module's public workflow by computing stage enabled.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        stages (list[str]): Pipeline stage names requested by the caller.
        stage (str): Single pipeline stage name being checked.
    
    Returns:
        bool: Boolean decision used by the caller to choose the next pipeline step.
    """
    return stage in stages


def _documents_for_extraction(
    documents,
    incremental_records: list[IncrementalFetch],
):
    """Return current documents that should continue through extraction.

    Args:
        documents (Any): Current fetched documents.
        incremental_records (list[IncrementalFetch]): Optional incremental
            comparison records.

    Returns:
        Any: Documents to extract. In non-incremental runs, every fetched
        document is returned.
    """

    if not incremental_records:
        return documents
    changed_ids = changed_document_ids(incremental_records)
    return [document for document in documents if document.document_id in changed_ids]


def _check_access(
    items,
    sources: list[Source],
    *,
    policy: FetchPolicy,
    robots_text_provider: Callable[[Source, FetchPolicy], str | None] | None,
) -> list[AccessDecision]:
    """Support the module's public workflow by computing check access.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        items (Any): Discovered crawl items being limited, checked, fetched, or
            converted.
        sources (list[Source]): Source registry entries available to the current
            pipeline step.
        policy (FetchPolicy): Fetch policy containing user-agent, timeout, retry, and
            rate-limit settings.
        robots_text_provider (Callable[[Source, FetchPolicy], str | None] | None): Value
            named ``robots_text_provider`` supplied by the caller for this pipeline
            step.
    
    Returns:
        list[AccessDecision]: Result produced for the next pipeline step or caller.
    """
    source_by_id = {source.source_id: source for source in sources}
    robots_cache: dict[str, str | None] = {}
    decisions: list[AccessDecision] = []
    for item in items:
        source = source_by_id[item.source_id]
        robots_text = None
        if source.robots_required:
            if source.source_id not in robots_cache:
                provider = robots_text_provider or _fetch_robots_text
                robots_cache[source.source_id] = provider(source, policy)
            robots_text = robots_cache[source.source_id]
        decisions.append(evaluate_access(item, source, policy=policy, robots_text=robots_text))
    return decisions


def _fetch_robots_text(source: Source, policy: FetchPolicy) -> str | None:
    """Support the module's public workflow by computing fetch robots text.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        source (Source): Source registry entry that explains where a document or URL
            came from.
        policy (FetchPolicy): Fetch policy containing user-agent, timeout, retry, and
            rate-limit settings.
    
    Returns:
        str | None: Result produced for the next pipeline step or caller.
    """
    request = Request(
        source_robots_url(source.base_url),
        headers=make_headers(policy),
        method="GET",
    )
    try:
        response = build_opener().open(request, timeout=policy.timeout_seconds)
        try:
            return response.read().decode("utf-8", errors="replace")
        finally:
            close = getattr(response, "close", None)
            if callable(close):
                close()
    except (OSError, URLError):
        return None


def _sources_by_claim_id(claims, documents, sources: list[Source]) -> dict[str, Source]:
    """Support the module's public workflow by computing sources by claim id.
    
    This private helper keeps the public function small and testable. It is documented
    because new maintainers often need to inspect these helpers when debugging a crawl
    run.
    
    Args:
        claims (Any): Claim records extracted from cleaned and redacted documents.
        documents (Any): Fetched or extracted documents available to the current
            pipeline step.
        sources (list[Source]): Source registry entries available to the current
            pipeline step.
    
    Returns:
        dict[str, Source]: Result produced for the next pipeline step or caller.
    """
    documents_by_id = {document.document_id: document for document in documents}
    sources_by_id = {source.source_id: source for source in sources}
    result = {}
    for claim in claims:
        document = documents_by_id.get(claim.document_id)
        if document is None:
            continue
        source = sources_by_id.get(document.source_id)
        if source is not None:
            result[claim.claim_id] = source
    return result


if __name__ == "__main__":
    raise SystemExit(main())
