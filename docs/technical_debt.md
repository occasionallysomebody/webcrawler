# Technical Debt Register

This file tracks known technical debt, implementation shortcuts, and production
gaps. Update it when debt is discovered, accepted, actively worked, or resolved.

Status values:

- `open`: known debt that still needs work.
- `accepted`: deliberate tradeoff with no immediate remediation planned.
- `in_progress`: being addressed in the current milestone.
- `resolved`: fixed; keep a short note with the milestone or commit context.

## Open Debt

| ID | Area | Status | Priority | Debt | Impact | Likely Resolution |
| --- | --- | --- | --- | --- | --- | --- |
| TD-003 | Frontend | open | medium | Next UI has build verification but no automated UI tests. | Regressions in filters, map rendering, and evidence drawer behavior may be missed. | Add component tests and a browser smoke test for the analyst dashboard. |
| TD-007 | Dependencies | open | medium | `npm audit --omit=dev` reports two moderate findings through `next`/`postcss`. | Deployment security review will flag the frontend dependency tree. | Recheck after Next/PostCSS releases; upgrade without forcing a breaking downgrade path. |
| TD-009 | Testing dependencies | open | low | `python -m pytest` emits a Starlette/FastAPI TestClient deprecation warning about `httpx`. | Tests pass, but future dependency upgrades may require changing the test client setup. | Track FastAPI/Starlette guidance and update API tests when the replacement client path is stable. |

## Resolved Debt

| ID | Area | Resolved In | Resolution | Verification |
| --- | --- | --- | --- | --- |
| TD-008 | Repo hygiene | Documentation/Sphinx pass | Removed tracked Python `__pycache__` bytecode files and kept generated caches ignored. | `git rm -f src/crawler/__pycache__/__init__.cpython-313.pyc src/crawler/__pycache__/models.cpython-313.pyc` |
| TD-004 | Storage | Milestone 27 | Production storage now has a zero-cost SQLite adapter for run summaries, per-run records, review status, audit events, and artifact manifests while local JSONL mode remains the default. Managed PostgreSQL/object storage is now an optional future scale-up, not a blocker. | `python -m pytest tests/test_storage.py tests/test_api.py tests/test_runner.py` |
| TD-005 | Security | Milestone 22 | FastAPI data routes support bearer-token auth, the Next UI has optional Basic Auth plus a server-side API proxy, and analyst actions/exported evidence are written as audit JSONL events. | `python -m pytest tests/test_api.py` |
| TD-001 | Extraction | Milestone 23 | PDF extraction now uses PyMuPDF, returns text with page markers, records page count and per-page metadata, and keeps malformed PDFs as explicit failed extraction records. | `python -m pytest tests/test_extract.py` |
| TD-002 | Extraction | Milestone 23 | HTML extraction now prefers Trafilatura for article/report extraction with the deterministic parser retained as a fallback. | `python -m pytest tests/test_extract.py` |
| TD-006 | Operations | Milestone 24 | Runner now has `scheduled_crawl` and `incremental_crawl` presets, previous-run metadata loading, conditional fetch validators, incremental status records, and downstream skipping for unchanged documents. | `python -m pytest tests/test_runner.py` |

## Update Rules

- Add new rows when a shortcut becomes visible during implementation or review.
- Move rows to `Resolved Debt` when fixed; include the milestone and short
  verification note.
- Do not delete resolved debt immediately; keep it as project memory.
- Reference debt IDs from milestone notes when a milestone intentionally accepts
  or resolves a debt item.
