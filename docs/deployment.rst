Deployment Boundary
===================

Milestone 22 turns the local API and Next UI proof of concept into a deployable
internal application boundary. The implementation remains JSONL-first so local
runs stay reproducible, but deployments can point the API at a shared run
artifact path and require authenticated access before serving crawler evidence.

FastAPI Settings
----------------

The API reads deployment settings from environment variables:

``CRAWLER_ENV``
   Environment label such as ``local``, ``staging``, or ``production``.

``CRAWLER_RUN_STORAGE_PATH``
   Directory containing run folders. Each run folder still contains
   ``run_summary.json`` and ``records/*.jsonl``. Local development defaults to
   ``outputs/runs``; production can use a mounted or synchronized shared path.

``CRAWLER_AUDIT_LOG_PATH``
   JSONL file that stores analyst audit events. The default is
   ``outputs/audit/audit_events.jsonl``.

``CRAWLER_STORAGE_BACKEND``
   Storage adapter label. Use ``local_jsonl`` for local development,
   ``shared_filesystem`` for a mounted run folder, or ``sqlite`` for the
   zero-cost durable storage adapter added in Milestone 27.

``CRAWLER_RUN_DB_PATH``
   SQLite database path used when ``CRAWLER_STORAGE_BACKEND=sqlite``. The
   default is ``outputs/storage/webcrawler.sqlite``.

``CRAWLER_CORS_ORIGINS``
   Comma-separated exact browser origins allowed to call the API.

``CRAWLER_CORS_ORIGIN_REGEX``
   Optional controlled regex for preview origins.

``CRAWLER_API_TOKEN``
   Bearer token required by protected API routes when auth is enabled.

``CRAWLER_AUTH_REQUIRED``
   Boolean override. When unset, auth is required automatically if
   ``CRAWLER_API_TOKEN`` is configured.

Protected API Routes
--------------------

``/health`` remains public for deployment probes. Run data, raw record access,
map data, evidence export, audit writes, and the API-backed map shell use the
auth dependency when auth is configured. Callers send:

.. code-block:: text

   Authorization: Bearer <CRAWLER_API_TOKEN>
   X-Analyst-Id: analyst-or-service-account

``X-Analyst-Id`` is used in audit events. If it is missing, the API records
``authenticated-analyst``.

Audit Event Format
------------------

Audit events are appended as JSONL with this shape:

.. code-block:: json

   {
     "event_id": "audit-...",
     "event_type": "evidence_exported",
     "actor": "analyst-a",
     "created_at": "2026-06-04T12:00:00+00:00",
     "run_id": "crawl-live",
     "claim_id": "claim-1",
     "document_id": null,
     "source_id": null,
     "request_path": "/runs/crawl-live/evidence-export",
     "metadata": {
       "claim_count": 1,
       "document_count": 1,
       "source_count": 1
     }
   }

When ``CRAWLER_STORAGE_BACKEND=sqlite`` is enabled, the API still writes the
JSONL audit log and also mirrors audit events into the SQLite ``audit_events``
table.

Production Storage
------------------

Milestone 27 keeps the project at a ``$0`` storage cost by using SQLite plus a
configured filesystem path. The runner writes the normal JSONL run folder first,
then mirrors run summaries, per-run records, review status, audit events, and
artifact manifests into SQLite.

Run a production-storage crawl locally:

.. code-block:: powershell

   python -m crawler.runner --run-id sqlite-demo --stages automatic_crawl --max-sources 3 --max-items-per-source 2 --max-fetches 3 --storage-backend sqlite --run-db-path outputs/storage/webcrawler.sqlite

Serve the API from SQLite:

.. code-block:: powershell

   $env:CRAWLER_STORAGE_BACKEND='sqlite'
   $env:CRAWLER_RUN_DB_PATH='outputs/storage/webcrawler.sqlite'
   python -m uvicorn crawler.api:app --host 127.0.0.1 --port 8000

Raw cache files, generated reports, logs, and static HTML exports remain
filesystem artifacts. SQLite stores their manifest paths so the run stays
auditable without storing large binary objects in the database.

Frontend Deployment
-------------------

The Next UI calls its same-origin proxy at ``/api/crawler/*`` by default. The
proxy forwards requests to ``CRAWLER_API_BASE_URL`` and attaches
``CRAWLER_API_TOKEN`` server-side, so the API token does not need to be exposed
as a ``NEXT_PUBLIC_*`` variable.

Set these variables for an internal deployment:

.. code-block:: text

   CRAWLER_API_BASE_URL=https://<fastapi-host>
   CRAWLER_API_TOKEN=<same-token-as-api>
   ANALYST_UI_USERNAME=<basic-auth-user>
   ANALYST_UI_PASSWORD=<basic-auth-password>
   ANALYST_ID=<audit-actor-label>

The Basic Auth proxy boundary is enabled only when a username or password is set.
For local unauthenticated demos, leave those values unset.

Hosting Choice
--------------

Use Vercel when the priority is the fastest path to a managed Next.js frontend
with preview and production environment variables. The FastAPI backend still
needs a separate hosted API or a supported backend service path, and the UI must
point ``CRAWLER_API_BASE_URL`` at that backend.

Use Coolify or a similar self-hosted open-source platform when the priority is
running the Next UI, FastAPI API, scheduled crawler, shared run storage, and
backups under one private server or VPS. This is usually a better fit while the
product still depends on local/shared filesystem run artifacts and scheduled
Python crawl jobs.

Client Review Gate
------------------

Before sharing a reviewer URL with clients:

- run a bounded crawl against approved public sources;
- serve that run through the FastAPI API;
- point the Next UI at the API through the same-origin proxy;
- keep demo overlays disabled unless explicitly labeled;
- verify run selection, filters, layer toggles, evidence drawer selection,
  refresh, and evidence export all perform real actions;
- remove any visible button or control that is not wired to a real action.

Verification
------------

The CI workflow in ``.github/workflows/ci.yml`` runs:

.. code-block:: powershell

   python -m pytest
   python -m ruff check .
   cd frontend
   npm.cmd run build
