# Implementation Plan

## 1. Purpose

This document defines the build sequence for a reusable public-source crawling and analysis pipeline.

It is intentionally task agnostic. Domain-specific goals, source lists, customer framing, and research questions belong in `goal.md`. Technology choices and scalability guidance belong in `techstack.md`.

Use this file to decide what to build next, how to verify it, and what counts as done.
Known implementation shortcuts and production gaps are tracked in
`docs/technical_debt.md`; update that file when new debt is discovered or when a
milestone resolves existing debt.
Docstrings and Sphinx pages are maintained as first-class project artifacts.
Follow `docs/documentation_policy.rst` for every new or changed module.

## 2. Build Strategy

Build the system in thin, testable layers:

1. Define data contracts.
2. Load a source registry.
3. Check access rules.
4. Discover candidate URLs or records.
5. Fetch permitted content.
6. Extract readable text.
7. Clean and normalize content.
8. Redact unnecessary sensitive data.
9. Extract entities and claims.
10. Score confidence and trust.
11. Store records with provenance.
12. Generate cited outputs.
13. Add automation, monitoring, and UI only after the pipeline is reliable.

Each milestone should produce a visible artifact: a file, table, log, report, or test result.

## 3. Definition Of Done

A milestone is done only when:

- The relevant code or document exists.
- The output format is documented.
- At least one happy-path example works.
- Obvious failure cases are handled.
- The result can be reproduced from a command, notebook cell, or documented manual step.
- Any assumptions are written down.
- Any new or resolved technical debt is reflected in `docs/technical_debt.md`.
- New or changed code has beginner-friendly Google-style docstrings and is
  exported through the Sphinx documentation in `docs/`.
- The next milestone is clear.

Do not treat "code was written" as done. Treat "code produced a verified artifact" as done.

## 4. Milestone 0: Project Skeleton

Create the basic repository structure.

Target files and folders:

```text
data/
docs/
notebooks/
outputs/
src/crawler/
tests/fixtures/
pyproject.toml
```

Acceptance criteria:

- The folder structure exists.
- The project has a short `README.md` explaining how to start.
- The project has a Python dependency manifest, preferably `pyproject.toml`.
- The dependency manifest includes dev tooling needed to run verification, at
  minimum `pytest`.
- Generated files have a documented destination.
- Temporary caches are separate from long-term outputs.

## 5. Milestone 1: Data Models

Define stable records for the pipeline.

Minimum models:

- `Source`
- `CrawlRun`
- `DiscoveredItem`
- `FetchedDocument`
- `ExtractedDocument`
- `CleanDocument`
- `Claim`
- `TrustScore`

Acceptance criteria:

- Each model has required fields and optional fields.
- Each model can be serialized to JSON.
- Example records exist in `tests/fixtures/`.
- Storage code can depend on these models without knowing the domain.

## 6. Milestone 2: Source Registry

Create a source registry loader.

Minimum fields:

- `source_id`
- `name`
- `tier`
- `publisher_type`
- `base_url`
- `access_method`
- `rate_limit_seconds`
- `robots_required`
- `notes`
- `enabled`

Acceptance criteria:

- The loader reads a CSV file.
- Invalid rows produce clear errors.
- Disabled sources are skipped.
- The loader does not require domain-specific fields.

## 7. Milestone 3: Access And Politeness

Implement access checks before fetching content.

Required behavior:

- Read `robots.txt` when required.
- Apply per-source rate limits.
- Use clear `User-Agent` headers.
- Respect timeouts.
- Log skipped URLs and the reason they were skipped.

Acceptance criteria:

- Allowed and disallowed examples are tested.
- Fetch code cannot run without a timeout.
- Fetch code records access decisions.
- The pipeline never bypasses access controls.

## 8. Milestone 4: Discovery

Implement the first discovery method.

Allowed discovery methods:

- Manual seed URLs.
- Sitemap parsing.
- RSS or Atom feed parsing.
- Public API query.
- Search-result page parsing only when allowed.

Acceptance criteria:

- Discovery returns normalized `DiscoveredItem` records.
- Duplicate URLs are removed.
- Each item keeps its source and discovery method.
- Discovery can run without fetching full document content.

## 9. Milestone 5: Fetching

Implement a targeted fetcher.

Required behavior:

- Fetch only permitted URLs.
- Save status code, content type, final URL, retrieval time, and checksum.
- Store raw content only in the configured cache location.
- Avoid repeated downloads when checksum or HTTP caching metadata shows no change.

Acceptance criteria:

- One HTML page can be fetched.
- One PDF or binary file can be fetched or explicitly skipped.
- Failed fetches are logged without stopping the full run.
- Raw cache paths are recorded.

## 10. Milestone 6: Extraction

Convert fetched content into text and metadata.

Extractor types:

- HTML extractor.
- PDF extractor.
- Plain-text extractor, if needed.

Acceptance criteria:

- Extractors return a common `ExtractedDocument` shape.
- Extraction method is recorded.
- Empty or low-quality extraction is flagged.
- The original URL and source metadata are preserved.

## 11. Milestone 7: Cleaning And Normalization

Clean extracted text.

Required behavior:

- Remove boilerplate where practical.
- Normalize whitespace.
- Preserve paragraphs.
- Keep source metadata separate from content.
- Detect language if useful.

Acceptance criteria:

- Cleaning is deterministic.
- Tests cover common boilerplate and whitespace cases.
- The cleaned output is readable enough for analyst review.
- The raw extracted text is not silently overwritten.

## 12. Milestone 8: Redaction

Redact unnecessary sensitive data before long-term storage.

Initial redaction targets:

- Emails.
- Phone numbers.
- Personal addresses when detected.
- Other project-defined sensitive patterns.

Acceptance criteria:

- Redaction rules are documented.
- Redacted text marks replacements clearly.
- Original sensitive text is not stored in long-term cleaned outputs unless explicitly allowed.
- Tests cover each redaction pattern.

## 13. Milestone 9: Entity And Claim Extraction

Extract structured signals from clean documents.

Initial approach:

- Use dictionaries and regex for transparent extraction.
- Store model-assisted extraction as a later optional layer.

Acceptance criteria:

- Extracted entities include type, text, source document, and confidence.
- Extracted claims include evidence excerpts.
- The pipeline can run even when no entities or claims are found.
- Extraction rules are easy to inspect and update.

## 14. Milestone 10: Trust Scoring

Attach simple confidence and trust fields.

Initial scoring inputs:

- Source tier.
- Publisher type.
- Freshness.
- Corroboration count.
- Source independence.
- Conflict flag.
- Extraction quality.

Acceptance criteria:

- Scores are explainable.
- The score calculation is deterministic.
- Missing data lowers confidence or marks uncertainty.
- Trust scores do not hide the underlying evidence.

## 15. Milestone 11: Storage

Persist pipeline records.

Initial storage:

- JSONL for append-only records.
- SQLite for structured querying.

Acceptance criteria:

- Records can be inserted and queried.
- Records keep provenance.
- Duplicate documents are handled by URL and checksum.
- Schema changes are documented.

## 16. Milestone 12: Reporting

Generate an analyst-ready output.

Output formats:

- Markdown.
- CSV.
- Notebook.
- JSON export.

Acceptance criteria:

- Reports cite source URLs.
- Reports include confidence and uncertainty.
- Reports distinguish evidence from interpretation.
- Reports list known gaps.

## 17. Milestone 13: Automation

Add repeatable pipeline execution.

Initial automation:

- One command that runs a configured subset of sources.
- Run logs.
- Output directory per run.

Later automation:

- Scheduler.
- Workflow orchestrator.
- Alerting.
- Dashboard.

Acceptance criteria:

- A run can be repeated.
- Failed stages are visible.
- Partial failures do not corrupt previous outputs.
- The run produces a summary file.

## 18. Milestone 14: Productization

Add product-facing components only after the core pipeline is reliable.

Possible additions:

- API service.
- Analyst UI.
- Authentication.
- Role-based access.
- Object storage.
- Distributed workers.
- Observability.
- Deployment automation.

Acceptance criteria:

- Product features reuse the same pipeline records.
- UI or API output links back to evidence.
- Access control and audit logging are planned before multi-user use.

Initial analyst UI decision:

- Build a map-first Azerbaijan energy intelligence dashboard before adding a
  heavier multi-user web stack.
- Use MapLibre GL JS with token-free vector tiles for the static demo artifact.
- Keep the app Python-first by generating HTML from pipeline records.
- Show ranked drillsite opportunities, environmental pressure zones, political
  pressure zones, source coverage, and an evidence drawer linked to source URLs.
- Treat Mapbox as an optional polish/vendor-service choice and CARTO as a later
  spatial-analytics choice, not the default for the first demo.

## 19. Milestone 15: Live UI Data Integration

Transition the product UI from mock operational overlays to pipeline-backed
records.

Required behavior:

- Load map inputs from a run-local `records/` directory.
- Use `sources.jsonl` for source coverage.
- Use `fetched_documents.jsonl` or `documents.jsonl` for citations.
- Use `claims.jsonl` for evidence-backed map markers.
- Use `trust_scores.jsonl` for confidence display.
- Keep hardcoded drillsite and pressure overlays behind an explicit demo flag.

Acceptance criteria:

- The runner's `build_map_ui` stage passes its run records into the UI builder.
- The UI renders claim markers from JSONL records without custom frontend code.
- Claim detail panels show source URL, evidence excerpt, and trust confidence
  when available.
- Demo overlays are opt-in and are not required for a functional map artifact.
- Tests cover JSONL record loading and generated HTML map payloads.

## 20. Milestone 16: Automatic Crawl Orchestration

Move from starter source data toward an automatically refreshed production
pipeline.

Required behavior:

- Provide an `automatic_crawl` runner preset that expands to source validation,
  discovery, access checks, fetching, extraction, cleaning, redaction, signal
  extraction, trust scoring, and map UI generation.
- Keep crawling bounded with `--max-sources`, `--max-items-per-source`,
  `--max-fetches`, timeouts, robots checks, and source rate limits.
- Treat `data/sources.csv` as a seed registry, not the whole production source
  system.
- Write every intermediate record to the run-local `records/` directory so the
  UI can consume live outputs without custom frontend changes.

Acceptance criteria:

- A single command can run the full bounded crawl pipeline.
- Fetch failures and extraction failures are recorded without corrupting the run.
- The generated map reads claim and trust records from the same run directory.
- Tests verify the full crawl-to-map path with injected network responses.
- Future production work can replace manual seeds with sitemap, feed, API, or
  approved-source discovery without changing UI contracts.

## 21. Milestone 17: Approved Source Expansion

Expand crawl targets from approved source-registry endpoints instead of relying
only on one manually curated URL per source.

Required behavior:

- Read `sitemap_url`, `rss_url`, and `api_url` from source metadata.
- Parse sitemap `<loc>` URLs.
- Parse RSS and Atom link URLs.
- Parse simple JSON API payloads with `url`, `link`, or `href` fields.
- Keep manual source URLs as fallback seeds.
- Keep expanded discovery bounded by `--max-items-per-source`.

Acceptance criteria:

- Expanded discovery can run without fetching discovered document content.
- `automatic_crawl` includes expanded discovery by default.
- Tests cover sitemap, feed, API, and runner integration with injected
  responses.
- Network or parse failures for discovery endpoints produce no expanded URLs
  but do not fail the run.

## 22. Milestone 18: Source Health And Frontier Management

Prepare the crawler for repeat production runs.

Status: implemented.

Required behavior:

- Track per-source fetch success, access denials, extraction failures, and claim
  yield.
- Identify stale, noisy, blocked, and high-value sources.
- Maintain a crawl frontier that can prioritize fresh approved URLs over repeated
  manual seeds.
- Preserve run-level audit logs for source health decisions.

Acceptance criteria:

- A run summary can rank sources by health and yield.
- Retry candidates are recorded separately from permanent skips.
- The next run can avoid repeatedly fetching known-bad URLs.

Implemented artifacts:

- `records/source_health.jsonl`
- `records/retry_candidates.jsonl`
- `assess_source_health` stage in `automatic_crawl`
- Tests for high-value sources, blocked/degraded sources, retryable candidates,
  permanent skips, and runner integration.

## 23. Milestone 19: Source Onboarding Workflow

Add a controlled path for growing beyond the starter CSV.

Status: implemented.

Required behavior:

- Store proposed sources separately from approved sources.
- Require analyst or operator approval before crawling a new domain.
- Record access method, robots policy, rate limit, allowed paths, blocked paths,
  source tier, and known limitations.

Acceptance criteria:

- Approved sources can be promoted into the active registry.
- Rejected or pending sources are not crawled.
- Every active source has access-control metadata.

Implemented artifacts:

- `data/proposed_sources.csv`
- `crawler.onboarding` CLI with `template`, `validate`, and `promote`
  commands.
- Proposed-source validation for status, proposer metadata, reviewer metadata,
  crawlable access method, and conservative rate limits.
- Promotion that appends only approved rows to the active source registry and
  skips existing source IDs.
- Tests for loading, validation failures, promotion, duplicate skips, and
  template generation.

## 24. Milestone 20: API-Backed Production UI

Move from static generated HTML toward a production app boundary.

Status: implemented.

Required behavior:

- Serve run records through a small API.
- Keep the map JSON contract compatible with the static artifact.
- Add filters for run, source, claim type, trust score, and freshness.
- Plan authentication and audit logging before multi-user deployment.

Acceptance criteria:

- The UI can load map data without embedding all records in HTML.
- Existing JSONL run artifacts remain exportable and auditable.
- Static HTML generation remains available for offline reports.

Implemented artifacts:

- `crawler.api` FastAPI app.
- `GET /health`, `GET /runs`, `GET /runs/{run_id}/summary`,
  `GET /runs/{run_id}/records/{record_name}`, and
  `GET /runs/{run_id}/map-data`.
- `GET /runs/{run_id}/map` API-backed map shell that fetches live map data.
- Map filters for source ID, claim type, minimum trust score, and demo overlays.
- Static map generation can be configured with an API base URL and run ID, while
  still retaining embedded data as an offline fallback.
- Tests for run listing, summaries, record serving, map-data serving, filters,
  API-backed map serving, unknown runs, and unsafe record names.
- `fastapi` and `uvicorn` project dependencies.

Next production direction:

- Build a Vercel/Next.js analyst frontend against this FastAPI contract.
- Add auth/RBAC and audit logging before multi-user deployment.
- Move durable run storage from JSONL/SQLite toward PostgreSQL/object storage
  when multiple users or scheduled jobs need shared state.

## 25. Milestone 21: Next.js/Vercel Analyst UI POC

Build a polished frontend POC against the FastAPI API contract.

Status: implemented.

Required behavior:

- Keep the Python crawler and FastAPI API as the backend.
- Add a separate Next.js app suitable for Vercel hosting.
- Load runs from `GET /runs`.
- Load map data from `GET /runs/{run_id}/map-data`.
- Provide run selection, claim type and trust filters, layer toggles, and an
  evidence drawer.
- Use MapLibre for the Azerbaijan map.

Acceptance criteria:

- The frontend builds with `npm run build`.
- Local dev server can load the FastAPI API through CORS.
- The POC defaults to the highest-claim run and renders live claim markers.
- Vercel deployment only needs `NEXT_PUBLIC_API_BASE_URL` configured.

Implemented artifacts:

- `frontend/package.json`
- `frontend/app/page.jsx`
- `frontend/app/layout.jsx`
- `frontend/app/globals.css`
- FastAPI CORS configuration for local Next development and Vercel preview URLs.

Next production direction:

- Deploy the Next UI against a hosted FastAPI backend.
- Add authenticated analyst access before exposing non-local runs.
- Add audit logs for run selection, exported evidence, and analyst notes.
- Move shared production run artifacts out of local `outputs/` storage.
- Add CI checks for Python tests, ruff, and `frontend` builds.

## 26. Milestone 22: Deployment, Auth, and Shared Run Storage

Harden the milestone 21 POC into a deployable internal application.

Status: implemented.

Required behavior:

- Protect the FastAPI API and Next UI with an authentication boundary.
- Record audit events for sensitive analyst actions and exported evidence.
- Support environment-specific API base URLs, CORS origins, and deployment
  settings.
- Define a shared storage path for production run artifacts, such as object
  storage plus PostgreSQL metadata, while preserving local JSONL development.
- Add CI commands that verify the Python backend and the `frontend` app.

Acceptance criteria:

- A deployed UI can access only the configured API origin.
- Unauthorized API requests are rejected.
- Analyst actions that affect evidence review or exports are auditable.
- Run listings and map data can come from shared production storage.
- CI runs `python -m pytest`, `python -m ruff check .`, and
  `npm.cmd run build` in `frontend`.

Debt addressed:

- TD-004, TD-005.

Implemented artifacts:

- Environment-driven API deployment settings in `crawler.config`.
- FastAPI bearer-token protection for run, record, map-data, audit, map, and
  evidence-export endpoints when auth is configured.
- Analyst audit records in `outputs/audit/audit_events.jsonl` by default, with
  `POST /audit-events` and audited `GET /runs/{run_id}/evidence-export`.
- Configurable run storage root through `CRAWLER_RUN_STORAGE_PATH`, preserving
  local JSONL development while allowing deployments to mount or sync shared
  run artifacts outside `outputs/`.
- Exact CORS origin configuration through `CRAWLER_CORS_ORIGINS` and optional
  controlled preview regex through `CRAWLER_CORS_ORIGIN_REGEX`.
- Next.js same-origin API proxy that keeps `CRAWLER_API_TOKEN` server-side, plus
  optional UI Basic Auth through `ANALYST_UI_USERNAME` and
  `ANALYST_UI_PASSWORD`.
- GitHub Actions workflow that runs `python -m pytest`,
  `python -m ruff check .`, and `npm.cmd run build` in `frontend`.

Next production direction:

- Replace the shared-filesystem JSONL storage root with managed PostgreSQL
  metadata and object storage adapters in Milestone 27.
- Add UI smoke tests and dependency hardening in Milestone 29.

## 27. Milestone 23: Production Extractors

Replace prototype extraction with reliable, source-aware extraction for public
HTML pages and PDF reports.

Status: implemented.

Required behavior:

- Add a production HTML extractor, such as `trafilatura` or `readability-lxml`,
  behind the existing extraction contract.
- Add PDF extraction with page-level provenance using `pymupdf` or `pdfplumber`.
- Preserve source URL, retrieval time, content type, page number where relevant,
  title, publication date hints, and extraction quality.
- Keep unsupported or failed extraction explicit in records and logs.
- Add fixture tests for HTML boilerplate removal, article extraction, PDF text,
  malformed content, and extraction failure records.

Acceptance criteria:

- Public HTML reports produce cleaner text than the prototype parser.
- Public PDF reports produce page-linked extracted text.
- Extraction errors do not stop the crawl run.
- Existing downstream cleaning, redaction, claim extraction, trust scoring, and
  map data contracts still work.
- `docs/technical_debt.md` is updated for TD-001 and TD-002.

Debt addressed:

- TD-001, TD-002.

Implemented artifacts:

- `crawler.extract` now prefers Trafilatura for public HTML extraction and
  retains the prior deterministic parser as a fallback for malformed or low
  signal pages.
- PDF extraction uses PyMuPDF and records page count, PDF metadata, and
  per-page text-length/word-count metadata while preserving the common
  `ExtractedDocument` contract.
- Malformed PDFs and failed extractor calls return explicit failed extraction
  records instead of stopping a crawl.
- Runtime dependencies now include `trafilatura` and `pymupdf`.
- Tests cover HTML boilerplate behavior, PDF text extraction, page metadata,
  malformed PDF failure records, and batch continuation.

Next production direction:

- Add scheduled incremental crawls, freshness windows, dedupe, and change
  detection in Milestone 24.

## 28. Milestone 24: Scheduler And Incremental Crawls

Move from manual bounded runs to repeat monitoring cycles.

Status: implemented.

Required behavior:

- Add a scheduler entry point for recurring approved-source crawls.
- Track freshness windows, last successful fetch, checksums, ETags, and
  last-modified values where available.
- Avoid refetching unchanged documents unless the source health policy requires
  it.
- Record new, changed, unchanged, failed, and skipped items separately.
- Keep command-line bounded crawl controls for local reproducibility.

Acceptance criteria:

- A scheduled run can resume from previous run metadata.
- Unchanged content is detected and logged without duplicating claim records.
- Changed content creates a new versioned document record.
- Source health uses incremental results.
- `docs/technical_debt.md` is updated for TD-006.

Debt addressed:

- TD-006.

Implemented artifacts:

- `scheduled_crawl` and `incremental_crawl` runner presets for recurring
  approved-source monitoring.
- `--previous-run-id` support plus automatic latest-prior-run detection when a
  previous run is not supplied.
- `records/incremental_fetches.jsonl` with `new`, `changed`, `unchanged`,
  `failed`, and `skipped` statuses.
- Conditional fetch reuse through prior ETag and Last-Modified metadata.
- Downstream extraction, cleaning, redaction, signal extraction, and trust
  scoring are skipped for unchanged documents to avoid duplicate claim records.
- Run summaries include previous run ID and incremental status counts.
- FastAPI can serve `incremental_fetches` through the record endpoint.

Next production direction:

- Make corroboration and contradiction visible in reports, API responses, and
  the analyst UI in Milestone 25.

## 29. Milestone 25: Corroboration And Contradiction Detection

Promote extracted claims from isolated records into cross-source intelligence.

Status: implemented.

Required behavior:

- Cluster similar claims by entity, asset, topic, location, and time window.
- Count corroborating sources by source tier and publisher type.
- Flag contradictions between official, corporate, NGO, academic, and media
  sources.
- Add explainable corroboration and conflict fields to trust scoring.
- Expose corroboration and contradiction status through reports, API responses,
  and the analyst UI.

Acceptance criteria:

- Similar claims from independent sources are grouped without losing individual
  citations.
- Conflicting claims are visible and cited.
- Trust scores include corroboration and conflict explanations.
- Reports and map detail panels show source agreement or disagreement.

Implemented artifacts:

- `crawler.corroboration` clusters related claims by claim type and normalized
  entities using deterministic local rules.
- `ClaimCluster` records are written to `records/claim_clusters.jsonl` with
  `single_source`, `corroborated`, or `conflicted` status.
- The runner includes `detect_corroboration` in automatic, incremental, and
  scheduled crawls before trust scoring.
- Trust scoring now uses claim clusters for corroborating sources and conflict
  penalties.
- Claim records, map features, Markdown reports, and the Next evidence drawer
  expose source agreement or disagreement context.
- FastAPI serves `claim_clusters` through the record endpoint.

Zero-cost implementation note:

- Corroboration is intentionally local and rule-based. Do not add Snowflake,
  paid NLP services, or hosted vector databases for this milestone.

Next production direction:

- Add analyst review decisions, review notes, and review-status API/UI fields in
  Milestone 26.

## 30. Milestone 26: Analyst Review Workflow

Add human review so the system supports due-diligence workflows instead of only
automated summaries.

Status: not started.

Required behavior:

- Let analysts mark claims as confirmed, rejected, needs review, or watchlisted.
- Store analyst notes separately from extracted source evidence.
- Keep review events auditable with user, timestamp, run ID, and claim ID.
- Add evidence export packets for selected claims, sources, and map zones.
- Preserve immutable original crawler records.

Acceptance criteria:

- Analyst decisions do not overwrite extracted claims.
- Review status is visible in API responses and the UI.
- Exported evidence packets include citations, retrieval metadata, trust fields,
  and review notes.
- Audit records can reconstruct who reviewed or exported evidence.

## 31. Milestone 27: Production Storage Implementation

Implement shared run storage after the storage boundary is defined.

Status: not started.

Required behavior:

- Store run metadata, sources, documents, claims, trust scores, review status,
  and audit events in a durable database.
- Store raw cache artifacts, extracted text, reports, and exports in object
  storage or a configured filesystem adapter.
- Keep local JSONL mode for development and reproducible tests.
- Add migrations or schema versioning for production tables.
- Add repository/service abstractions only where they simplify API and runner
  integration.

Acceptance criteria:

- The API can list and serve runs from shared storage.
- The runner can write production records without breaking local mode.
- Tests cover both local and production storage adapters where practical.
- Run artifacts remain auditable and exportable.

Debt addressed:

- TD-004.

## 32. Milestone 28: Observability And Source Operations

Make the production crawler operable by surfacing health, failures, freshness,
and source yield.

Status: not started.

Required behavior:

- Emit structured metrics for crawl duration, source success, fetch failures,
  extraction failures, claim yield, retries, and skipped access decisions.
- Add operational dashboards or API endpoints for source health and run health.
- Add alert rules for stale high-value sources, repeated failures, and sudden
  claim-yield changes.
- Keep logs safe for compliance review and avoid raw sensitive content in logs.

Acceptance criteria:

- Operators can identify stale, blocked, noisy, and high-yield sources quickly.
- Alerts include source ID, run ID, reason, and recommended next action.
- Metrics distinguish access, fetch, extraction, and signal-quality failures.
- Operational views do not expose unnecessary raw content.

## 33. Milestone 29: CI/CD And Dependency Hardening

Make verification and deployment repeatable.

Status: not started.

Required behavior:

- Add CI for Python tests, ruff, frontend install, frontend build, and audit
  reporting.
- Add an explicit deployment path from local development to a hosted client
  environment: Vercel for the Next UI plus hosted FastAPI, or a self-hosted
  stack such as Coolify when one-box operations, private networking, and
  filesystem/object-storage control matter more than managed frontend hosting.
- Add dependency update policy for Python and Node packages.
- Add deployment checks for API environment variables, CORS origins, auth
  settings, and frontend API base URL.
- Add browser smoke testing for the analyst UI.
- Browser smoke tests must verify real API-backed crawled records are shown and
  that interactive controls are functional, including run selection, filters,
  layer toggles, evidence drawer selection, refresh, and evidence export.
- Document rollback and local reproduction steps.

Acceptance criteria:

- CI blocks changes that break backend tests, linting, or frontend builds.
- Dependency audit findings are documented or resolved before production
  deployment.
- Browser smoke tests verify the map page loads and can fetch live API data.
- A deployed reviewer URL shows records extracted from crawled/scraped approved
  sources, not hardcoded mock claims or demo-only overlays.
- Buttons and controls used in the demo perform real actions or are removed
  before client review.
- Deployment configuration can be reproduced from documentation.

Debt addressed:

- TD-003, TD-007.

## 34. Milestone 30: Evaluation Pack And Commercial Demo Readiness

Package the Azerbaijan case study into a credible proof-of-concept demo for
technical, compliance, and business audiences.

Status: not started.

Required behavior:

- Define a fixed evaluation source set and time window.
- Produce a cited Azerbaijan energy intelligence brief from representative
  crawler runs.
- Include source coverage, known gaps, trust-score explanations, contradictions,
  and analyst review examples.
- Add a reproducible demo script that starts the API, frontend, and a selected
  run.
- Include a client-review deployment checklist with the chosen hosting path,
  auth settings, seeded real crawl run, and disabled demo overlays.
- Document what is production-ready, what is prototype-only, and which debt
  remains open.

Acceptance criteria:

- A reviewer can reproduce the demo from documented commands.
- The UI shows live API-backed run data, not hardcoded intelligence overlays.
- All visible client-facing buttons and filters are functional against the live
  API-backed dataset.
- The report cites every claim and includes uncertainty notes.
- The technical debt register matches the demo limitations.
- The project can justify the next investment decision: stop, pilot, or build
  toward production.

## 35. Working Rules

- Prefer small changes with visible outputs.
- Keep domain logic configurable.
- Keep source access rules separate from extraction logic.
- Keep raw caches separate from cleaned outputs.
- Do not add a heavier tool until the simpler version is limiting real work.
- Keep Google-style docstrings and Sphinx API pages current with code changes.
- Update this plan when the project changes direction.
