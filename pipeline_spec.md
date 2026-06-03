# Pipeline Specification

## 1. Purpose

This document defines the reusable pipeline contract for public-source discovery, ingestion, extraction, analysis, and reporting.

It is task agnostic. Domain-specific topics, source priorities, and target customers belong in `goal.md`.

## 2. Pipeline Contract

The pipeline accepts a source registry and optional run configuration, then produces structured records, cleaned text, extracted claims, trust scores, logs, and reports.

High-level flow:

```text
source registry
    -> validate sources
    -> discover items
    -> check access
    -> fetch content
    -> extract text
    -> clean text
    -> redact sensitive data
    -> extract entities
    -> extract claims
    -> score trust
    -> store records
    -> generate outputs
```

Each stage must be runnable independently for debugging.

## 3. Inputs

### Source Registry

Default path:

```text
data/sources.csv
```

Required fields:

- `source_id`
- `name`
- `tier`
- `publisher_type`
- `base_url`
- `access_method`
- `rate_limit_seconds`
- `robots_required`
- `enabled`
- `notes`

Optional fields:

- `sitemap_url`
- `rss_url`
- `api_url`
- `allowed_paths`
- `blocked_paths`
- `language`
- `country`
- `domain_tags`
- `known_bias_or_limitation`

### Run Configuration

Default path:

```text
config/run.yaml
```

Suggested fields:

- `run_id`
- `max_sources`
- `max_items_per_source`
- `max_fetches`
- `cache_raw`
- `output_dir`
- `respect_robots`
- `default_timeout_seconds`
- `default_user_agent`
- `enabled_stages`

The pipeline should use safe defaults if no run configuration exists.

## 4. Outputs

Each run should create a timestamped run directory:

```text
outputs/runs/<run_id>/
  logs/
  raw_cache/
  extracted/
  cleaned/
  records/
  reports/
  run_summary.json
```

Long-term structured storage may also write to:

```text
data/crawler.sqlite
data/documents.jsonl
data/claims.jsonl
```

## 5. Stage Specifications

### Stage 1: Validate Sources

Input:

- Source registry.

Output:

- Validated source records.
- Validation errors.

Rules:

- Skip disabled sources.
- Reject rows without `source_id`, `name`, `base_url`, or `access_method`.
- Warn when `rate_limit_seconds` is missing.
- Do not infer sensitive source behavior from the domain topic.

### Stage 2: Discover Items

Input:

- Validated sources.

Output:

- `DiscoveredItem` records.

Allowed methods:

- Manual seed URL.
- Sitemap.
- RSS or Atom.
- Public API.
- Allowed HTML index page.

Required fields:

- `item_id`
- `source_id`
- `url`
- `discovery_method`
- `discovered_at`
- `title`
- `published_at`
- `content_type_hint`

Rules:

- Normalize URLs.
- Remove exact duplicates.
- Preserve discovery method.
- Do not fetch full content during discovery unless the access method requires it.

### Stage 3: Check Access

Input:

- `DiscoveredItem` records.
- Source access rules.

Output:

- Access decisions.

Required fields:

- `item_id`
- `url`
- `allowed`
- `reason`
- `checked_at`

Rules:

- Respect `robots.txt` when configured.
- Respect explicit source registry blocks.
- Do not bypass paywalls, logins, CAPTCHA, or anti-bot controls.
- Log skipped items.

### Stage 4: Fetch Content

Input:

- Allowed items.

Output:

- `FetchedDocument` records.

Required fields:

- `document_id`
- `source_id`
- `url`
- `final_url`
- `status_code`
- `content_type`
- `retrieved_at`
- `checksum`
- `raw_cache_path`
- `fetch_error`

Rules:

- Use configured timeout.
- Use configured User-Agent.
- Apply per-source rate limits.
- Store raw content only when allowed by configuration.
- Continue the run after individual fetch failures.

### Stage 5: Extract Text

Input:

- `FetchedDocument` records.

Output:

- `ExtractedDocument` records.

Required fields:

- `document_id`
- `source_id`
- `url`
- `title`
- `published_at`
- `extracted_text`
- `extraction_method`
- `extraction_quality`
- `page_count`
- `error`

Rules:

- Use content-type-specific extractors.
- Preserve document provenance.
- Mark empty or very short extraction as low quality.
- Do not discard failed extraction records.

### Stage 6: Clean Text

Input:

- `ExtractedDocument` records.

Output:

- `CleanDocument` records.

Required fields:

- `document_id`
- `clean_text`
- `cleaning_method`
- `word_count`
- `language`
- `quality_flags`

Rules:

- Normalize whitespace.
- Remove obvious boilerplate.
- Preserve paragraph boundaries.
- Keep text transformations deterministic.

### Stage 7: Redact Sensitive Data

Input:

- `CleanDocument` records.

Output:

- Redacted clean documents.
- Redaction log.

Required fields:

- `document_id`
- `redacted_text`
- `redaction_count`
- `redaction_types`

Rules:

- Redact unnecessary PII before long-term storage.
- Use visible placeholders such as `[REDACTED_EMAIL]`.
- Keep redaction rules configurable.
- Do not store sensitive originals in cleaned outputs unless the run configuration explicitly allows it.

### Stage 8: Extract Entities

Input:

- Redacted clean documents.

Output:

- Entity records.

Required fields:

- `entity_id`
- `document_id`
- `entity_type`
- `entity_text`
- `normalized_text`
- `evidence_excerpt`
- `confidence`

Rules:

- Start with transparent dictionaries and patterns.
- Keep domain dictionaries configurable.
- Allow zero extracted entities.

### Stage 9: Extract Claims

Input:

- Redacted clean documents.
- Entity records.

Output:

- Claim records.

Required fields:

- `claim_id`
- `document_id`
- `claim_text`
- `claim_type`
- `entities`
- `evidence_excerpt`
- `extraction_method`
- `confidence`

Rules:

- Claims must include evidence excerpts.
- Claims must preserve source URL through `document_id`.
- LLM-assisted extraction must return structured records and should be reviewable.

### Stage 10: Score Trust

Input:

- Source records.
- Document records.
- Claim records.

Output:

- Trust score records.

Required fields:

- `claim_id`
- `source_tier_score`
- `freshness_score`
- `corroboration_score`
- `independence_score`
- `conflict_penalty`
- `final_score`
- `score_explanation`

Rules:

- Scores must be explainable.
- Missing evidence should reduce confidence.
- Conflicting evidence should be visible, not hidden.
- The final score is not a substitute for citations.

### Stage 11: Store Records

Input:

- All pipeline records.

Output:

- JSONL files.
- SQLite tables.

Rules:

- Use stable IDs.
- Use checksums for deduplication.
- Preserve run IDs.
- Never overwrite previous runs without explicit instruction.

### Stage 12: Generate Reports

Input:

- Stored records.
- Optional analysis question.

Output:

- Markdown, CSV, JSON, or notebook report.

Rules:

- Cite source URLs.
- Include confidence and uncertainty.
- Separate evidence from interpretation.
- Include known gaps.
- Include run metadata.

## 6. Error Handling

Errors should be structured and logged.

Minimum error fields:

- `run_id`
- `stage`
- `source_id`
- `item_id`
- `document_id`
- `error_type`
- `message`
- `retryable`
- `created_at`

The pipeline should continue after item-level failures and stop only for configuration, schema, or storage failures that make the run invalid.

## 7. Idempotency And Incremental Runs

The pipeline should support repeated runs.

Rules:

- Stable IDs should derive from source ID, normalized URL, and checksum where practical.
- Existing documents should not be reprocessed unless content changed or the user requests reprocessing.
- Runs should produce separate summaries.
- Incremental behavior should be visible in logs.

## 8. Logging

Each run should log:

- Sources loaded.
- Sources skipped.
- Items discovered.
- Access decisions.
- Fetch attempts.
- Extraction quality.
- Redaction counts.
- Entity and claim counts.
- Trust-score counts.
- Storage writes.
- Report outputs.

## 9. Quality Metrics

Track these metrics per run:

- Number of enabled sources.
- Number of discovered items.
- Number of allowed items.
- Number of fetched documents.
- Fetch success rate.
- Extraction success rate.
- Average cleaned word count.
- Redaction count.
- Entity count.
- Claim count.
- Number of claims with corroboration.
- Number of claims with conflicts.

## 10. Automation Behavior

The automated pipeline should:

- Read project docs before running.
- Validate configuration before network calls.
- Run only enabled stages.
- Respect source limits.
- Produce a run summary.
- Stop before risky or undefined behavior.

The automated pipeline should not:

- Add new domains without registry updates.
- Ignore access checks.
- Delete prior outputs without explicit instruction.
- Convert uncertain claims into confident findings.
- Hide failed stages.

## 11. Run Summary Schema

Each run should produce:

```json
{
  "run_id": "example-run-id",
  "started_at": "ISO-8601 timestamp",
  "finished_at": "ISO-8601 timestamp",
  "status": "success | partial_success | failed",
  "enabled_stages": [],
  "sources_loaded": 0,
  "items_discovered": 0,
  "documents_fetched": 0,
  "documents_extracted": 0,
  "documents_cleaned": 0,
  "claims_extracted": 0,
  "trust_scores_created": 0,
  "errors": [],
  "outputs": []
}
```

## 12. Extension Points

The pipeline should support future replacement of:

- CSV registry with database-backed source management.
- `httpx` fetcher with Scrapy spiders.
- SQLite with PostgreSQL.
- Local raw cache with object storage.
- Rule-based extraction with model-assisted extraction.
- Manual reports with API or UI-driven reports.

The data contracts should remain stable across these upgrades.
