# Tech Stack And Architecture Plan

## 1. Design Principle

Build the first version as a small, auditable Python pipeline, but choose interfaces that can scale into a commercial intelligence platform.

The system should grow in layers:

1. **Local proof of concept:** Simple scripts, CSV/JSONL, SQLite, and notebooks.
2. **Research prototype:** Scheduled pipelines, stronger metadata, DuckDB analytics, repeatable extraction, and claim scoring.
3. **Commercial pilot:** PostgreSQL, object storage, background jobs, API service, analyst UI, authentication, and observability.
4. **Production platform:** Distributed crawling, queue-based ingestion, multi-tenant access controls, monitoring, audit logs, and deployment automation.

Do not start with the production platform. Start with clean module boundaries so production components can replace local ones without rewriting the whole project.

## 2. Recommended MVP Stack

### Language And Runtime

- **Python 3.12+**
- **uv** for dependency and virtual environment management.
- **ruff** for linting and formatting.
- **pytest** for tests.
- **pre-commit** once the project has more than a few files.

Python is the right first language because the project is data-heavy, uses web extraction, needs notebooks, and will likely include NLP, entity extraction, and RAG.

### HTTP And Crawling

- **httpx** for targeted HTTP requests.
- **urllib.robotparser** for first-pass `robots.txt` checks.
- **tenacity** for controlled retries, if retry logic becomes repeated.
- **Scrapy** later, when multi-domain crawling, spider scheduling, retry policies, and crawl pipelines become necessary.

Start with `httpx` because the proof of concept should fetch known URLs from a source registry. Move to Scrapy only after the project has clear source types and crawl rules.

### HTML And PDF Extraction

- **trafilatura** for extracting main article/report text from HTML.
- **BeautifulSoup4** for custom parsing of source pages, sitemaps, and structured lists.
- **PyMuPDF** for PDF text extraction.
- **pdfplumber** later if table extraction becomes important.

The extraction layer should return one common document shape no matter where the text came from.

### Local Storage

- **CSV** for the first source registry.
- **JSONL** for raw-ish extracted document records.
- **SQLite** for structured metadata, documents, claims, runs, and trust scores.
- **DuckDB** for local analytical queries across CSV, JSONL, Parquet, and SQLite exports.

SQLite keeps the proof of concept easy to understand. DuckDB gives strong analytical power without requiring a server.

### Analysis And NLP

- **pandas** for tabular inspection.
- **rapidfuzz** for deduplicating titles, URLs, company names, and asset names.
- **regex and controlled dictionaries** for the first entity and risk-topic tagger.
- **spaCy** later for named-entity recognition.
- **LLM structured extraction** later for claim extraction, source comparison, and analyst summaries.

Start with transparent rules before using heavier NLP. This makes the pipeline easier to validate and easier to explain to researchers or corporate users.

### RAG And Search

- **SQLite full-text search** for the earliest searchable corpus.
- **PostgreSQL + pgvector** when embeddings and multi-user access become necessary.
- **Hybrid retrieval** later: keyword search plus vector search plus metadata filters.

Do not add a vector database until the metadata, cleaning, source provenance, and claim schema are reliable.

### Analyst Interface

- **Jupyter notebooks** for early analysis.
- **Streamlit** for the first analyst-facing demo.
- **FastAPI** later for a product API.
- **React or Next.js** later only if the product needs a polished multi-user web app.

The first demo should prove the intelligence workflow: source coverage, claims, confidence, citations, and changes over time.

## 3. Future-Proof Architecture

Use a modular pipeline with stable data contracts:

```text
source registry
    -> discovery
    -> fetch
    -> extract
    -> clean
    -> redact
    -> entity tag
    -> claim extract
    -> trust score
    -> store
    -> search / retrieve
    -> analyze / report
```

Each stage should read and write plain Python objects or typed records. Avoid hiding data transformations inside one large script.

Recommended package layout:

```text
webcrawler/
  data/
    sources.csv
  docs/
  src/
    crawler/
      __init__.py
      config.py
      models.py
      robots.py
      discover.py
      fetch.py
      extract_html.py
      extract_pdf.py
      clean.py
      redact.py
      entities.py
      claims.py
      trust.py
      storage.py
      reporting.py
  tests/
    fixtures/
    test_robots.py
    test_clean.py
    test_trust.py
  notebooks/
  outputs/
```

The key future-proofing move is `models.py`: define the document, source, claim, and crawl-run schemas early. Storage can change later if the records stay stable.

## 4. Core Data Models

### Source

Fields:

- `source_id`
- `name`
- `tier`
- `publisher_type`
- `base_url`
- `access_method`
- `robots_notes`
- `rate_limit_seconds`
- `known_bias_or_limitation`
- `last_checked_at`

### Document

Fields:

- `document_id`
- `source_id`
- `url`
- `title`
- `publisher`
- `published_at`
- `retrieved_at`
- `content_type`
- `language`
- `raw_cache_path`
- `clean_text`
- `checksum`
- `extraction_method`

### Claim

Fields:

- `claim_id`
- `document_id`
- `claim_text`
- `companies`
- `assets`
- `locations`
- `risk_category`
- `evidence_excerpt`
- `confidence_level`
- `corroborating_document_ids`
- `conflicting_document_ids`
- `analyst_notes`

### Trust Score

Fields:

- `claim_id`
- `source_tier_score`
- `freshness_score`
- `corroboration_score`
- `independence_score`
- `conflict_penalty`
- `final_score`
- `score_explanation`

These fields are intentionally simple. The scoring system should be explainable before it becomes sophisticated.

## 5. Scalability Path

### Phase 1: Local MVP

Use:

- Python scripts.
- CSV source registry.
- JSONL document outputs.
- SQLite metadata store.
- Jupyter notebook or Markdown report.

Goal:

- Process 8-12 Azerbaijan energy-sector sources.
- Produce one cited mini analyst report.
- Demonstrate source tiers, provenance, entity tagging, and trust scoring.

### Phase 2: Repeatable Research Prototype

Add:

- `pyproject.toml`.
- Tests and fixtures.
- DuckDB analytical queries.
- Scheduled local runs.
- Better source registry validation.
- Incremental fetches using checksums and `Last-Modified` or `ETag` headers when available.

Goal:

- Re-run the same collection process and show what changed.

### Phase 3: Commercial Pilot

Replace or add:

- PostgreSQL for durable multi-user metadata.
- pgvector for embeddings.
- S3, Azure Blob, GCS, or MinIO for raw documents and PDFs.
- Prefect for orchestration.
- FastAPI for an internal API.
- Streamlit or React for an analyst interface.
- Authentication and role-based access.

Goal:

- Support multiple monitored regions, repeatable jobs, analyst review, and exportable evidence packages.

### Phase 4: Production Platform

Add:

- Distributed crawl workers.
- Queue system such as Redis Queue, Celery, or cloud-native queues.
- Centralized logging and metrics.
- Audit logs.
- Secrets management.
- CI/CD.
- Containerized deployment.
- Tenant isolation if selling to multiple companies.

Goal:

- Operate as a reliable, monitored commercial intelligence service.

## 6. Storage Evolution

Use this migration path:

```text
CSV / JSONL
    -> SQLite
    -> DuckDB analytics
    -> PostgreSQL
    -> PostgreSQL + pgvector
    -> object storage for raw documents
```

Avoid MongoDB for the first version unless the data becomes highly variable and document-shaped in a way that SQLite/PostgreSQL cannot handle. The core records are relational enough that SQL is a better default.

Avoid Snowflake for the first version. It is useful for enterprise-scale analytics, but it adds cost and operational complexity before the data model is proven.

## 7. Crawling Evolution

Use this migration path:

```text
manual seed URLs
    -> httpx targeted fetcher
    -> sitemap / RSS / API discovery
    -> Scrapy spiders
    -> queued distributed workers
```

The first crawler should be boring, polite, and explainable. Commercial credibility comes from provenance and repeatability, not aggressive crawling.

## 8. RAG Evolution

Use this migration path:

```text
manual cited summaries
    -> SQLite full-text search
    -> keyword + metadata search
    -> embeddings in pgvector
    -> hybrid retrieval
    -> LLM-generated reports with citation checks
```

Every generated answer should link back to source records and document excerpts. Do not let RAG bypass the evidence ledger.

## 9. Trust And Validation Layer

This is the most important differentiator for the project.

The trust layer should start with simple fields:

- Source tier.
- Publisher type.
- Retrieval date.
- Publication date.
- Source independence.
- Corroboration count.
- Conflict flag.
- Whether the claim comes from a stakeholder source.
- Whether the claim is repeated across independent sources.

Later, the trust layer can add:

- Temporal change detection.
- Source reliability histories.
- Citation graph analysis.
- Claim clustering.
- Anomaly detection across source streams.
- Human analyst review feedback.
- Uncertainty estimates.

This is where the project best connects to CYNICS-style research: public web data can be treated as a noisy, adversarial, partially observable signal stream.

## 10. Security And Compliance Defaults

Implement these from the beginning:

- Respect `robots.txt`.
- Use rate limits.
- Send clear, polite `User-Agent` headers.
- Do not bypass access controls.
- Do not scrape private or sensitive systems.
- Keep raw document caches separate from cleaned outputs.
- Redact unnecessary PII before long-term storage.
- Keep source metadata and retrieval logs.
- Add a deletion path for temporary raw files.
- Keep secrets out of source control.

For a commercial pilot, add:

- Environment-based configuration.
- Secrets manager integration.
- Role-based access control.
- Audit logs.
- Data retention policy.
- Legal review of monitored sources.

## 11. Recommended Initial Dependencies

For the first implementation:

```toml
[project]
dependencies = [
  "httpx",
  "beautifulsoup4",
  "trafilatura",
  "pymupdf",
  "pandas",
  "duckdb",
  "rapidfuzz",
  "pydantic",
]

[dependency-groups]
dev = [
  "pytest",
  "ruff",
]
```

Add later only when needed:

- `scrapy` for larger crawling.
- `prefect` for orchestration.
- `spacy` for NLP.
- `fastapi` for API service.
- `streamlit` for analyst demo.
- `psycopg` and `pgvector` for PostgreSQL vector search.

## 12. First Build Recommendation

Start with these files:

1. `data/sources.csv`
2. `src/crawler/models.py`
3. `src/crawler/robots.py`
4. `src/crawler/fetch.py`
5. `src/crawler/extract_html.py`
6. `src/crawler/storage.py`
7. `notebooks/azerbaijan_demo.ipynb`

The first milestone should be modest: fetch and parse one permitted source, save provenance, extract clean text, and produce a small cited note. Once that works, add PDFs, entity tagging, and trust scoring.
