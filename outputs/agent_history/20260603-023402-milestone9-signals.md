# Run Summary

- Task attempted: Run Milestone 9 by adding transparent entity and claim extraction.
- Milestone advanced: Milestone 9 - Entity And Claim Extraction.
- Files changed: `src/crawler/models.py`, `src/crawler/signals.py`, `tests/test_models.py`, `tests/test_signals.py`, `tests/fixtures/model_examples.json`, `README.md`, and this run summary.
- What changed: Added an `Entity` record, dictionary/regex entity extraction, simple risk/context claim extraction from redacted text, evidence excerpts, stable entity and claim IDs, zero-result handling, batch extraction, and structured signal log entries.
- Verification performed: Direct README-style validation printed `3 1 environmental_risk`; `python -m pytest` collected and passed 41 tests.
- Decisions made: Kept extraction deterministic and dependency-free. Entity dictionaries are intentionally small and inspectable so later work can move them to configuration.
- Next task: Start Milestone 10 with deterministic trust scoring for extracted claims.
