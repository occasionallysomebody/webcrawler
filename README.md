# Webcrawler

This repository hosts a small, auditable public-source crawling pipeline. The
project is intentionally staged: start with local files and testable modules,
then add more pipeline stages only after each earlier stage produces a verified
artifact.

## Client-Friendly Overview

| Question | Short answer | What this means in practice |
| --- | --- | --- |
| What is this project? | This is a public-source intelligence crawler that collects approved web pages and reports, extracts useful text, finds risk claims, scores source confidence, and shows the results in an analyst dashboard. | It turns scattered public information into cited, reviewable evidence so a client can see where each finding came from. |
| What is the use case? | The demo use case is monitoring Azerbaijan oil and gas risks for environmental, governance, operational, and reputational signals. | A client can review what public sources say about assets, companies, topics, and changes over time without relying on mock data. |
| How do you run the project? | Install the project once, run one crawler command to create real records, start the API, then start the web dashboard. | In VS Code, open a terminal, run `cd C:\repos\webcrawler`, run `python -m pip install -e ".[dev]"`, run `python -m crawler.runner --run-id demo-client --stages automatic_crawl --max-sources 3 --max-items-per-source 2 --max-fetches 3`, run `python -m uvicorn crawler.api:app --host 127.0.0.1 --port 8000`, open a second terminal, run `cd C:\repos\webcrawler\frontend`, run `npm.cmd install`, run `npm.cmd run dev`, and open `http://127.0.0.1:3000`. |
| What technologies are used and why? | Python runs the crawler, FastAPI serves the records, Next.js builds the dashboard, MapLibre shows map data, JSONL keeps evidence auditable, SQLite supports local querying, Trafilatura extracts HTML, and PyMuPDF extracts PDFs. | This stack keeps the prototype inspectable, testable, and usable at `$0` locally before any paid hosting decision is made. |
| What is this project, and what is it not? | It is a proof-of-concept public-source intelligence pipeline, not a fully hosted commercial SaaS, not a private-data scraper, not a paywall bypass tool, and not a replacement for analyst or legal review. | The scope is approved public sources, real crawled records, transparent evidence, and functional dashboard controls, while always-on hosting and enterprise compliance remain out of scope for the local demo. |
| What "production level" is this crawler? | It is a strong local prototype with production-shaped boundaries, but it is not yet a full production crawler. | It already has auth, audit logs, scheduled incremental crawls, extraction, trust scoring, corroboration checks, and a dashboard, but still needs durable production storage, analyst review workflow, observability, browser smoke tests, and deployment hardening. |
| What resources would it take to build a production-level crawler? | A production version would need hosted compute, durable database storage, object storage, monitoring, backups, secure deployment, source review, and ongoing maintenance. | With the current `$0` preference, use local demos or free tiers; a serious always-on client deployment would usually require owned hardware or paid hosting plus at least one engineer and one analyst/compliance reviewer. |

## Client Demo Checklist

| Step | What to do | What the client should see |
| --- | --- | --- |
| 1. Open the project folder | In the VS Code terminal, run `cd C:\repos\webcrawler`. | The terminal prompt is inside the project root before any Python command runs. |
| 2. Install Python dependencies | Run `python -m pip install -e ".[dev]"`. | Python can find the crawler code and its required libraries. |
| 3. Create crawler records | Run `python -m crawler.runner --run-id demo-client --stages automatic_crawl --max-sources 3 --max-items-per-source 2 --max-fetches 3`. | The project creates local evidence files from approved public websites. |
| 4. Start the backend | In that same `C:\repos\webcrawler` terminal, run `python -m uvicorn crawler.api:app --host 127.0.0.1 --port 8000` and leave it running. | The dashboard has a local API that can read the crawler records. |
| 5. Open the dashboard folder | Open a second VS Code terminal and run `cd C:\repos\webcrawler\frontend`. | The second terminal is inside the dashboard folder before any npm command runs. |
| 6. Install dashboard dependencies | Run `npm.cmd install`. | The dashboard has the local JavaScript packages it needs. |
| 7. Start the dashboard | Run `npm.cmd run dev` and leave it running. | The web app starts locally without paid hosting. |
| 8. Open the dashboard | Visit `http://127.0.0.1:3000`. | The client can use the buttons, filters, map, source list, claims, trust scores, corroboration status, and evidence export against real crawled data. |
| 9. Keep cost at `$0` | Run locally first and avoid paid cloud services until a production pilot is approved. | Vercel free tier may work for the frontend, but the current safest `$0` path is a local demo because the crawler and API need a running backend. |

The demo command limits crawling to 3 sources only so a client can see results
quickly; this is not a product limit, and real monitoring should use limits
that match the approved source registry, crawl schedule, and politeness rules.
If Step 3 says `No module named crawler` or `ModuleNotFoundError`, rerun Step 2
from `C:\repos\webcrawler` and then run Step 3 again from that same folder.
If the VS Code PowerShell terminal blocks a command or behaves differently from
these steps, open a new VS Code terminal with Command Prompt and run the same
`cd` and command lines there.

## Current Status

The repository has the project skeleton, initial data models, and source
registry/access/discovery/fetching layers in place.

- Milestone 0: project skeleton is complete.
- Milestone 1: data models are implemented in `src/crawler/models.py`.
- Milestone 2: source registry loading is implemented in
  `src/crawler/source_registry.py`.
- Milestone 3: access and politeness checks are implemented in
  `src/crawler/robots.py`.
- Milestone 4: manual seed discovery is implemented in
  `src/crawler/discovery.py`.
- Milestone 5: targeted fetching is implemented in `src/crawler/fetch.py`.
- Milestone 6: HTML and plain-text extraction are implemented in
  `src/crawler/extract.py`.
- Milestone 7: deterministic cleaning and normalization are implemented in
  `src/crawler/clean.py`.
- Milestone 8: sensitive-text redaction is implemented in
  `src/crawler/redact.py`.
- Milestone 9: transparent entity and claim extraction is implemented in
  `src/crawler/signals.py`.
- Milestone 10: deterministic trust scoring is implemented in
  `src/crawler/trust.py`.
- Milestone 11: JSONL and SQLite storage helpers are implemented in
  `src/crawler/storage.py`.
- Milestone 12: Markdown reporting is implemented in
  `src/crawler/reporting.py`.
- Milestone 13: repeatable local automation is implemented in
  `src/crawler/runner.py`.
- Milestone 14: a product-facing Azerbaijan analyst map UI is implemented in
  `src/crawler/map_ui.py` and can be generated by the local runner.
- Milestone 15: the map UI reads live pipeline JSONL records for sources,
  fetched documents, claims, and trust scores; hardcoded operational overlays
  are now an explicit demo fallback.
- Milestone 17: approved source expansion is implemented for sitemap, RSS/Atom,
  and simple JSON API endpoints from the seed registry.
- Milestone 18: source health and crawl frontier records are generated for
  repeat production runs.
- Milestone 19: proposed-source onboarding and approval are implemented before
  new domains can enter active crawling.
- Milestone 20: FastAPI-backed production UI API boundary is implemented while
  preserving the static map export.
- Milestone 21: a Next.js/Vercel-style analyst UI POC is implemented in
  `frontend/` and consumes the FastAPI API.
- Milestone 22: deployment settings, authenticated API access, analyst audit
  events, shared run storage configuration, and CI verification are implemented.
- Milestone 23: production HTML and PDF extractors are implemented with
  Trafilatura and PyMuPDF.
- Milestone 24: scheduled incremental crawls are implemented with previous-run
  comparison and unchanged-document skipping.
- Milestone 25: corroboration and contradiction detection are implemented with
  local deterministic claim clusters.

## Repository Layout

```text
data/              Source registries and durable local stores
docs/              Reusable project documentation and design notes
notebooks/         Manual analysis and validation notebooks
outputs/           Generated artifacts from agent runs and pipeline runs
src/crawler/       Pipeline modules
tests/fixtures/    Example records and test inputs
```

Known technical debt is tracked in `docs/technical_debt.md`. Update it when a
milestone accepts, discovers, or resolves implementation debt.

The detailed roadmap in `implementation_plan.md` currently extends through
Milestone 30, covering production extraction, scheduling, corroboration,
analyst review, storage, observability, CI/CD, and commercial demo readiness.

Developer documentation is built with Sphinx from `docs/` and Python
docstrings. Build it with:

```powershell
python -m pip install -e ".[dev]"
python -m sphinx -b html docs docs/_build/html
```

Generated outputs should stay under `outputs/`. Temporary raw caches belong in a
run-specific path such as `outputs/runs/<run_id>/raw_cache/`, separate from
long-term cleaned outputs and summaries.

## Quick Verification

From the repository root:

```powershell
Get-ChildItem data, docs, notebooks, outputs, src, tests
```

Successful output should list the scaffolded directories. As milestones are
implemented, add the smallest reproducible command for each new stage here.

## Validation

Install the local package and dev tools before running the full test suite:

```powershell
python -m pip install -e ".[dev]"
python -m pytest
```

If dev dependencies are not installed yet, use direct Python validation:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
python -c "from crawler.source_registry import load_source_registry; r=load_source_registry('data/sources.csv'); print(len(r.sources), len(r.skipped))"
```

Expected output:

```text
37 2
```

Milestone 4 manual seed discovery can be checked without network access:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
python -c "from crawler.discovery import discover_from_source_registry; items=discover_from_source_registry('data/sources.csv', discovered_at='2026-06-03T00:00:00+00:00'); print(len(items)); print(items[0].to_json())"
```

Expected first line:

```text
36
```

Milestone 5 targeted fetching can be checked without live network access by
using an injected opener:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
$env:PYTHONDONTWRITEBYTECODE='1'
@'
from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.fetch import fetch_item
from crawler.models import AccessDecision, DiscoveredItem


class Response:
    headers = {"Content-Type": "text/html"}

    def read(self):
        return b"<html>ok</html>"

    def getcode(self):
        return 200

    def geturl(self):
        return "https://example.org/report"


class Opener:
    def open(self, request, timeout):
        return Response()


item = DiscoveredItem(
    item_id="item-1",
    source_id="source-1",
    url="https://example.org/report",
    discovery_method="manual_seed",
    discovered_at="2026-06-03T00:00:00+00:00",
)
decision = AccessDecision(
    item_id=item.item_id,
    source_id=item.source_id,
    url=item.url,
    allowed=True,
    reason="allowed",
    checked_at="2026-06-03T00:00:01+00:00",
)
with TemporaryDirectory() as tmp_dir:
    doc = fetch_item(
        item,
        decision,
        cache_dir=tmp_dir,
        opener=Opener(),
        retrieved_at="2026-06-03T00:00:02+00:00",
    )
    print(doc.status_code, Path(doc.raw_cache_path).exists(), doc.checksum.startswith("sha256:"))
'@ | python -
```

Expected output:

```text
200 True True
```

Milestone 6 extraction can be checked from a temporary cached HTML file:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
$env:PYTHONDONTWRITEBYTECODE='1'
@'
from pathlib import Path
from tempfile import TemporaryDirectory

from crawler.extract import extract_document
from crawler.models import FetchedDocument

with TemporaryDirectory() as tmp_dir:
    html_path = Path(tmp_dir) / "doc.html"
    html_path.write_text(
        "<html><head><title>Example</title></head><body><main><p>Readable evidence text for extraction.</p></main></body></html>",
        encoding="utf-8",
    )
    fetched = FetchedDocument(
        document_id="doc-1",
        source_id="source-1",
        url="https://example.org/report",
        content_type="text/html; charset=utf-8",
        raw_cache_path=str(html_path),
    )
    extracted = extract_document(fetched)
    print(extracted.extraction_method, extracted.title, extracted.extraction_quality)
'@ | python -
```

Expected output:

```text
html_trafilatura Example low
```

Milestone 23 production PDF extraction can be checked from a temporary generated
PDF:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
$env:PYTHONDONTWRITEBYTECODE='1'
@'
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz

from crawler.extract import extract_document
from crawler.models import FetchedDocument

with TemporaryDirectory() as tmp_dir:
    pdf_path = Path(tmp_dir) / "report.pdf"
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "Public PDF evidence about Caspian energy reporting.")
    pdf.save(pdf_path)
    pdf.close()

    fetched = FetchedDocument(
        document_id="doc-1",
        source_id="source-1",
        url="https://example.org/report.pdf",
        content_type="application/pdf",
        raw_cache_path=str(pdf_path),
    )
    extracted = extract_document(fetched)
    print(extracted.extraction_method, extracted.page_count, extracted.error)
'@ | python -
```

Expected output:

```text
pdf_pymupdf 1 None
```

Milestone 7 cleaning can be checked from an extracted text record:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
$env:PYTHONDONTWRITEBYTECODE='1'
@'
from crawler.clean import clean_document
from crawler.models import ExtractedDocument

extracted = ExtractedDocument(
    document_id="doc-1",
    source_id="source-1",
    url="https://example.org/report",
    extracted_text="Accept all cookies\n\nUseful   evidence text for analyst review.\n\nShare this article",
    extraction_method="html",
    extraction_quality="medium",
)
cleaned = clean_document(extracted)
print(cleaned.clean_text)
print(cleaned.word_count, cleaned.quality_flags)
'@ | python -
```

Expected output:

```text
Useful evidence text for analyst review.
6 ['boilerplate_removed', 'short_text']
```

Milestone 8 redaction can be checked from a cleaned text record:

```powershell
$env:PYTHONPATH='C:\repos\webcrawler\src'
$env:PYTHONDONTWRITEBYTECODE='1'
@'
from crawler.models import CleanDocument
from crawler.redact import redact_document

cleaned = CleanDocument(
    document_id="doc-1",
    clean_text="Contact analyst@example.org or 202-555-0100.",
    cleaning_method="normalize_whitespace_v1",
    word_count=5,
)
redacted = redact_document(cleaned)
print(redacted.redacted_text)
print(redacted.redaction_count, redacted.redaction_types)
'@ | python -
```

Expected output:

```text
Contact [REDACTED_EMAIL] or [REDACTED_PHONE].
2 ['email', 'phone']
```

Milestone 9 signal extraction can be checked from a redacted text record:

```powershell
@'
from crawler.models import RedactedDocument
from crawler.signals import extract_signals

doc = RedactedDocument(
    document_id="doc-1",
    redacted_text="Global Witness reported gas flaring pollution in Azerbaijan.",
    redaction_method="regex_redaction_v1",
    redaction_count=0,
)
signals = extract_signals(doc)
print(len(signals.entities), len(signals.claims), signals.claims[0].claim_type)
'@ | python -
```

Expected output:

```text
3 1 environmental_risk
```

Milestone 10 trust scoring can be checked from a claim and source:

```powershell
@'
from crawler.models import Claim, Source
from crawler.trust import score_claim

claim = Claim(
    claim_id="claim-1",
    document_id="doc-1",
    claim_text="Methane emissions were reported in 2025.",
    claim_type="environmental_risk",
    entities=[{"entity_type": "date", "normalized_text": "2025"}],
    confidence=0.7,
)
source = Source("src-1", "Example", "tier_1", "multilateral", "https://example.org", "manual_seed")
score = score_claim(claim, source=source, as_of_year=2026)
print(score.final_score, score.source_tier_score, score.freshness_score)
'@ | python -
```

Expected output:

```text
0.662 0.95 0.9
```

Milestone 11 storage can be checked with a temporary SQLite database:

```powershell
@'
from pathlib import Path
from tempfile import TemporaryDirectory
from crawler.models import Source
from crawler.storage import fetch_records, initialize_sqlite, upsert_records

with TemporaryDirectory() as tmp:
    con = initialize_sqlite(Path(tmp) / "crawler.sqlite")
    upsert_records(con, [Source("src-1", "Example", "tier_1", "multilateral", "https://example.org", "manual_seed")])
    print(fetch_records(con, "Source")[0]["source_id"])
    con.close()
'@ | python -
```

Expected output:

```text
src-1
```

Milestone 12 reporting can be checked from one cited claim:

```powershell
@'
from crawler.models import Claim, FetchedDocument, Source, TrustScore
from crawler.reporting import generate_markdown_report

report = generate_markdown_report(
    title="Demo Report",
    claims=[Claim("claim-1", "doc-1", "Gas flaring pollution was reported.", "environmental_risk", evidence_excerpt="Gas flaring pollution was reported.")],
    trust_scores=[TrustScore("claim-1", final_score=0.8, score_explanation="demo")],
    documents=[FetchedDocument("doc-1", "source-1", "https://example.org/report")],
    sources=[Source("source-1", "Example", "tier_1", "multilateral", "https://example.org", "manual_seed")],
    known_gaps=["Demo input only."],
)
print(report.splitlines()[0])
print("https://example.org/report" in report)
'@ | python -
```

Expected output:

```text
# Demo Report
True
```

Milestone 13 automation can run the current network-free stages:

```powershell
python -m crawler.runner --run-id demo-local --stages validate_sources,discover_items
```

Expected output:

```text
outputs\runs\demo-local
success
```

The run writes `outputs/runs/demo-local/run_summary.json`, logs, and JSONL
records.

Milestone 14 map UI generation can be run with the same local runner:

```powershell
python -m crawler.runner --run-id demo-map --stages validate_sources,discover_items,build_map_ui
```

Expected output:

```text
outputs\runs\demo-map
success
```

Open `outputs/runs/demo-map/ui/azerbaijan_energy_map.html` in a browser to view
the MapLibre-based Azerbaijan operational dashboard.

Milestone 15 live-record UI integration uses the run's `records/` directory as
the map input. When present, these files are loaded into the evidence map:

```text
records/sources.jsonl
records/fetched_documents.jsonl
records/documents.jsonl
records/claims.jsonl
records/trust_scores.jsonl
```

The current local runner writes `sources.jsonl` and discovery records, so the
generated map shows live source coverage by default. As later runner stages
write fetched documents, claims, and trust scores into the same directory, the
map automatically adds evidence-backed claim markers with citations and trust
confidence. Demo drillsite and pressure overlays remain available in
`crawler.map_ui.build_map_data(..., include_demo_overlays=True)` for mockups,
but they are not the default production path.

## Next Step

Milestone 16 automatic crawl orchestration runs the full local pipeline from
seed registry to live map records:

```powershell
python -m crawler.runner --run-id crawl-live --stages automatic_crawl --max-sources 3 --max-items-per-source 1 --max-fetches 3 --timeout-seconds 10
```

The command respects source registry enablement, robots checks, configured rate
limits, fetch timeouts, and explicit fetch limits. It writes:

```text
records/access_decisions.jsonl
records/fetched_documents.jsonl
records/extracted_documents.jsonl
records/clean_documents.jsonl
records/redacted_documents.jsonl
records/entities.jsonl
records/claims.jsonl
records/trust_scores.jsonl
ui/azerbaijan_energy_map.html
```

`data/sources.csv` is now best understood as the initial seed registry. A
production deployment should grow it through scheduled source discovery,
approved source onboarding, sitemap/feed/API expansion, and run monitoring
rather than relying only on manually curated starter rows.

Milestone 17 source expansion is opt-in for discovery-only runs and included in
`automatic_crawl`. It reads approved endpoint columns from `data/sources.csv`:

```text
sitemap_url
rss_url
api_url
```

Discovery-only source expansion can be checked without fetching discovered
documents:

```powershell
python -m crawler.runner --run-id expanded-discovery --stages expand_discovery --max-sources 5 --max-items-per-source 10 --timeout-seconds 10
```

For full automatic crawl with expanded discovery, use a higher
`--max-items-per-source` than `1`; otherwise the manual seed may consume the
per-source item limit before sitemap/feed/API URLs are crawled.

```powershell
python -m crawler.runner --run-id crawl-expanded --stages automatic_crawl --max-sources 3 --max-items-per-source 10 --max-fetches 5 --timeout-seconds 10
```

Production continuation milestones:

- Milestone 20: production UI service boundary, replacing static HTML artifacts
  with an API-backed app while preserving the current JSONL record contract.

Milestone 18 source health and frontier management is included in
`automatic_crawl` as `assess_source_health`. It writes:

```text
records/source_health.jsonl
records/retry_candidates.jsonl
```

`source_health.jsonl` ranks each source by access success, fetch success,
extraction success, and claim yield. `retry_candidates.jsonl` separates
retryable failures, such as transient fetch errors or missing robots lookup,
from permanent skips that need policy or extractor review.

Milestone 19 source onboarding keeps proposed sources separate from active
crawling. Proposed rows go in:

```text
data/proposed_sources.csv
```

Create or refresh the proposal template:

```powershell
python -m crawler.onboarding template --path data/proposed_sources.csv
```

Validate proposed sources before review:

```powershell
python -m crawler.onboarding validate --proposed data/proposed_sources.csv
```

Promote only approved rows into the active registry:

```powershell
python -m crawler.onboarding promote --proposed data/proposed_sources.csv --active data/sources.csv
```

Only `proposal_status=approved` rows with reviewer metadata and crawl-safe
access settings are promoted. `proposed` and `rejected` rows are never crawled
because `automatic_crawl` reads only `data/sources.csv`.

Milestone 20 adds the product API boundary. FastAPI serves crawler run artifacts
and the same map JSON contract used by the static HTML export; Vercel/Next.js
remains the recommended frontend host for a polished analyst UI that consumes
this API.

Run the API locally:

```powershell
python -m uvicorn crawler.api:app --reload
```

Useful endpoints:

```text
GET /health
GET /runs
GET /runs/{run_id}/summary
GET /runs/{run_id}/records/{record_name}
GET /runs/{run_id}/map-data
GET /runs/{run_id}/map
```

Supported map filters:

```text
source_id
claim_type
min_trust
include_demo_overlays
```

Open the API-backed map for a run:

```text
http://127.0.0.1:8000/runs/crawl-health/map
```

That page uses the same map shell as the static export, but it refreshes its
data from `/runs/{run_id}/map-data`. The static HTML map remains available for
offline reports. To generate static HTML that also refreshes from a running API,
pass the API base URL during the crawl:

```powershell
python -m crawler.runner --run-id poc-crawl --stages automatic_crawl --max-sources 1 --max-items-per-source 1 --max-fetches 1 --timeout-seconds 10 --map-api-base-url http://127.0.0.1:8000
```

Production frontends, including a later Vercel/Next.js UI, should call
`/runs/{run_id}/map-data` directly.

Milestone 21 adds a separate frontend app for the analyst POC:

```text
frontend/
```

Run the FastAPI backend:

```powershell
python -m uvicorn crawler.api:app --host 127.0.0.1 --port 8000
```

Run the Next.js UI:

```powershell
cd frontend
npm.cmd install
$env:NEXT_PUBLIC_API_BASE_URL='http://127.0.0.1:8000'
npm.cmd run dev
```

Open:

```text
http://127.0.0.1:3000
```

For Vercel deployment, set:

```text
NEXT_PUBLIC_API_BASE_URL=https://<your-fastapi-api-host>
```

The Next UI provides run selection, live map-data loading, trust and claim-type
filters, layer toggles, source/claim counts, and an evidence drawer. It is a POC
frontend over the FastAPI contract, not a replacement for the Python crawler.

Milestone 22 adds the deployment hardening boundary. Local development still
works without auth by default:

```powershell
python -m uvicorn crawler.api:app --host 127.0.0.1 --port 8000
cd frontend
npm.cmd run dev
```

Environment templates are provided without real secrets:

```text
.env.example
frontend/.env.local.example
```

Copy them to `.env.local` in the relevant directory for local use. Real
`.env`, `.env.local`, and `.env.*.local` files are ignored by git at the repo
root and under `frontend/`.

For an internal deployment, configure the FastAPI API with exact origins,
shared run storage, an audit log path, and a bearer token:

```text
CRAWLER_ENV=production
CRAWLER_RUN_STORAGE_PATH=/mnt/webcrawler/runs
CRAWLER_AUDIT_LOG_PATH=/mnt/webcrawler/audit/audit_events.jsonl
CRAWLER_STORAGE_BACKEND=shared_filesystem
CRAWLER_CORS_ORIGINS=https://<your-next-ui-host>
CRAWLER_API_TOKEN=<shared-api-token>
CRAWLER_AUTH_REQUIRED=true
```

Configure the Next UI to use its same-origin proxy so the API token stays
server-side:

```text
CRAWLER_API_BASE_URL=https://<your-fastapi-api-host>
CRAWLER_API_TOKEN=<shared-api-token>
ANALYST_UI_USERNAME=<ui-user>
ANALYST_UI_PASSWORD=<ui-password>
ANALYST_ID=<audit-actor-label>
```

The frontend calls `/api/crawler/*` by default. That proxy forwards requests to
`CRAWLER_API_BASE_URL` with the API bearer token. `NEXT_PUBLIC_API_BASE_URL`
remains available for unauthenticated local direct-to-FastAPI demos.
`CRAWLER_API_TOKEN` is the same shared bearer token configured on the FastAPI
backend; it must not be exposed as a `NEXT_PUBLIC_*` value. `ANALYST_UI_USERNAME`
and `ANALYST_UI_PASSWORD` protect the Next UI with Basic Auth. `ANALYST_ID` and
`NEXT_PUBLIC_ANALYST_ID` are audit actor labels, not secrets.

Analyst audit records are appended as JSONL:

```text
outputs/audit/audit_events.jsonl
```

Each record includes `event_id`, `event_type`, `actor`, `created_at`, optional
run/claim/document/source IDs, the request path, and small metadata such as
filter values or exported record counts. The evidence drawer can export a
selected claim packet through `GET /runs/{run_id}/evidence-export`, which also
records an `evidence_exported` audit event.

CI verification is defined in `.github/workflows/ci.yml` and runs:

```powershell
python -m pytest
python -m ruff check .
cd frontend
npm.cmd run build
```

The next production milestone is scheduled incremental crawls: add freshness
windows, dedupe, unchanged-document handling, and change detection while
preserving the same downstream record contracts.

Milestone 24 adds scheduled incremental crawl controls. Use `scheduled_crawl`
when you want the runner to compare against a prior run and skip unchanged
documents downstream:

```powershell
python -m crawler.runner --run-id monitor-cycle-2 --stages scheduled_crawl --previous-run-id monitor-cycle-1 --max-sources 3 --max-items-per-source 10 --max-fetches 5
```

If `--previous-run-id` is omitted, the runner chooses the latest successful or
partially successful run with fetched document records under `outputs/runs`.
The run writes:

```text
records/incremental_fetches.jsonl
```

Each incremental record is classified as `new`, `changed`, `unchanged`,
`failed`, or `skipped`. Unchanged documents are recorded but do not continue
through extraction and claim generation, which prevents duplicate claims in
monitoring cycles.

For client-facing demos, use live API-backed runs with demo overlays disabled.
Every visible button or control in the deployed UI should either perform a real
action against the API-backed dataset or be removed before review. Vercel is a
good fit for the Next UI when the FastAPI backend is hosted separately. Coolify
or another self-hosted dashboard stack makes more sense when you want the API,
frontend, worker, storage path, and scheduled crawler on one private server.
Given the current `$0` constraint, prefer local demos, free-tier frontend
hosting, or hardware you already own. Do not introduce paid warehouse, database,
or hosting services unless that constraint changes.

Milestone 25 adds local claim clustering:

```text
records/claim_clusters.jsonl
```

Each cluster groups related claims and marks the agreement state as
`single_source`, `corroborated`, or `conflicted`. The runner includes this in
`automatic_crawl`, `incremental_crawl`, and `scheduled_crawl`, and trust scores,
reports, API records, map feature properties, and the Next evidence drawer use
the cluster context.
