Architecture Guide
==================

Why This Project Is Split Into Small Modules
--------------------------------------------

The project is not a generic scraper. It is an auditable intelligence pipeline.
Each module owns one stage so a developer can inspect the records produced by
that stage before trusting the next one. This matters because the eventual
analyst needs to know where a claim came from, whether the source was allowed to
be fetched, how the text was cleaned, and why a trust score was assigned.

Pipeline Stages
---------------

``source_registry``
   Loads approved sources from CSV. This is the first compliance boundary:
   sources that are disabled, malformed, or not approved should not enter the
   crawl.

``discovery``
   Turns approved source metadata into candidate URLs. It prefers manual seeds,
   sitemaps, RSS/Atom feeds, and approved API URLs before falling back to direct
   HTML pages.

``robots``
   Applies access and politeness rules. This keeps fetch behavior explainable
   and defensible for legal or compliance review.

``fetch``
   Downloads permitted content with timeouts, headers, cache paths, checksums,
   and structured error records. Fetching is separate from extraction so network
   failures do not get confused with parser failures.

``extract``
   Converts fetched bytes into readable text records. HTML extraction prefers
   Trafilatura and falls back to a deterministic standard-library parser when a
   page is malformed or too sparse. PDF extraction uses PyMuPDF and records page
   count plus per-page extraction metadata.

``clean`` and ``redact``
   Normalize extracted text, remove boilerplate, and redact unnecessary
   sensitive information before persistent downstream use.

``signals`` and ``trust``
   Extract entities and claims, then assign transparent trust scores. These
   modules intentionally use explainable rules first so the output can be
   audited before adding heavier NLP or RAG layers.

``corroboration``
   Groups related claims by claim type and normalized entities, then marks each
   group as single-source, corroborated, or conflicted. This gives reports, API
   responses, and map detail panels visible source agreement context without
   using paid external services.

``storage``
   Writes JSONL records for local inspection and mirrors production runs into
   SQLite when configured. SQLite stores run summaries, per-run records, review
   status, audit events, and artifact manifests without requiring paid managed
   storage.

``incremental``
   Loads previous run metadata, classifies current fetches as new, changed,
   unchanged, failed, or skipped, and lets scheduled crawls avoid duplicating
   downstream claims for unchanged content.

``reporting``, ``map_ui``, ``api``, and ``frontend``
   Turn pipeline records into analyst-facing outputs. The FastAPI service and
   Next UI consume the same run artifacts instead of inventing separate mock
   data paths.

``review``
   Stores append-only human review decisions for extracted claims. Review notes
   are separate from source evidence so original crawler records remain
   immutable.

``config`` and ``audit``
   Define the deployment boundary. ``config`` reads environment-specific API
   settings such as run storage paths, SQLite database paths, CORS origins, and
   bearer-token auth.
   ``audit`` appends JSONL records for analyst actions such as run selection,
   evidence inspection, and evidence export.

How To Read A Run
-----------------

A run under ``outputs/runs/<run_id>/`` usually contains:

``run_summary.json``
   High-level counters and stage status.

``records/*.jsonl``
   Stage-specific audit records. These are the best first place to debug.

``logs/run_events.jsonl``
   Structured events that explain what the runner did.

``ui/azerbaijan_energy_map.html``
   Static map output for offline review.

``../audit/audit_events.jsonl``
   Optional deployment audit log. The default location is
   ``outputs/audit/audit_events.jsonl`` and can be changed with
   ``CRAWLER_AUDIT_LOG_PATH``.

Deployment Boundary
-------------------

Local runs keep using ``outputs/runs`` unless configured otherwise. Deployed API
instances should set ``CRAWLER_RUN_STORAGE_PATH`` to a shared run-artifact
directory, ``CRAWLER_CORS_ORIGINS`` to the exact Next UI origin, and
``CRAWLER_API_TOKEN`` to require bearer-token auth for data routes. The Next UI
uses a same-origin proxy so the API token remains server-side.

Beginner Debugging Workflow
---------------------------

1. Open ``run_summary.json`` and confirm the expected stages ran.
2. Check ``records/source_health.jsonl`` for blocked or low-yield sources.
3. Inspect ``records/fetched_documents.jsonl`` before blaming extraction.
4. Inspect ``records/extracted_documents.jsonl`` before blaming claim logic.
5. Use ``records/claims.jsonl`` and ``records/trust_scores.jsonl`` to verify
   what appears in the report, API, or map.
