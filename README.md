# Webcrawler

This repository hosts a small, auditable public-source crawling pipeline. The
project is intentionally staged: start with local files and testable modules,
then add more pipeline stages only after each earlier stage produces a verified
artifact.

## Current Status

The repository is at the project skeleton stage. The basic folders for source
data, implementation code, tests, notebooks, and generated outputs are present,
but the pipeline stages are not implemented yet.

## Repository Layout

```text
data/              Source registries and durable local stores
docs/              Reusable project documentation and design notes
notebooks/         Manual analysis and validation notebooks
outputs/           Generated artifacts from agent runs and pipeline runs
src/crawler/       Pipeline modules
tests/fixtures/    Example records and test inputs
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

## Next Step

The next logical module is the pipeline data contract layer, starting with
stable records in `src/crawler/models.py` and example fixtures in
`tests/fixtures/`.
