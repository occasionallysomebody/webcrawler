# Implementation Plan

## 1. Purpose

This document defines the build sequence for a reusable public-source crawling and analysis pipeline.

It is intentionally task agnostic. Domain-specific goals, source lists, customer framing, and research questions belong in `goal.md`. Technology choices and scalability guidance belong in `techstack.md`.

Use this file to decide what to build next, how to verify it, and what counts as done.

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
```

Acceptance criteria:

- The folder structure exists.
- The project has a short `README.md` explaining how to start.
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

## 19. Working Rules

- Prefer small changes with visible outputs.
- Keep domain logic configurable.
- Keep source access rules separate from extraction logic.
- Keep raw caches separate from cleaned outputs.
- Do not add a heavier tool until the simpler version is limiting real work.
- Update this plan when the project changes direction.
