"""Repeatable local pipeline runner."""

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
from crawler.discovery import discover_expanded_source_urls, discover_manual_seed_urls
from crawler.extract import extract_documents, extraction_log_entry
from crawler.fetch import fetch_items, fetch_log_entry
from crawler.map_ui import map_ui_log_entry, write_map_ui
from crawler.models import AccessDecision, CrawlRun, Source
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


@dataclass(slots=True)
class RunResult:
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
    trust_scores = []
    source_health_records = []
    retry_candidates = []

    try:
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
            )
            append_jsonl(records_dir / "fetched_documents.jsonl", fetched_documents)
            for document in fetched_documents:
                _write_log(log_path, fetch_log_entry(document))

        if _stage_enabled(stages, "extract_documents"):
            extracted_documents = extract_documents(fetched_documents)
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
            append_jsonl(records_dir / "claims.jsonl", claims)

        if _stage_enabled(stages, "score_trust"):
            trust_scores = score_claims(
                claims,
                sources_by_claim_id=_sources_by_claim_id(claims, fetched_documents, sources),
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
        "trust_scores_created": len(trust_scores),
        "source_health_records": len(source_health_records),
        "retry_candidates": len(retry_candidates),
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
            str(records_dir / "trust_scores.jsonl"),
            str(records_dir / "source_health.jsonl"),
            str(records_dir / "retry_candidates.jsonl"),
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
            "score_trust,assess_source_health,build_map_ui,expand_discovery,"
            "automatic_crawl"
        ),
    )
    parser.add_argument("--max-sources", type=int)
    parser.add_argument("--max-items-per-source", type=int)
    parser.add_argument("--max-fetches", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=20.0)
    parser.add_argument("--user-agent", default="webcrawler/0.1")
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
    )
    print(result.output_dir)
    print(result.summary["status"])
    return 0 if result.summary["status"] == "success" else 1


def _limit_items_per_source(items, limit: int):
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
    entry = {"created_at": datetime.now(UTC).isoformat(), **entry}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(entry, sort_keys=True))
        handle.write("\n")


def _default_run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _expand_stages(stages: list[str]) -> list[str]:
    expanded: list[str] = []
    for stage in stages:
        if stage == "automatic_crawl":
            expanded.extend(AUTOMATIC_CRAWL_STAGES)
        else:
            expanded.append(stage)
    return list(dict.fromkeys(expanded))


def _needs_sources(stages: list[str]) -> bool:
    return any(
        stage in stages
        for stage in [
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
    )


def _needs_discovery(stages: list[str]) -> bool:
    return any(
        stage in stages
        for stage in [
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
        ]
    )


def _stage_enabled(stages: list[str], stage: str) -> bool:
    return stage in stages


def _check_access(
    items,
    sources: list[Source],
    *,
    policy: FetchPolicy,
    robots_text_provider: Callable[[Source, FetchPolicy], str | None] | None,
) -> list[AccessDecision]:
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
