# Run Summary

- Task attempted: Reformat `pasted-text.txt` into the current `data/sources.csv` schema and remove stale links.
- Files changed: `data/sources.csv` and this run summary.
- Source count: 39 registry rows total; 37 enabled sources and 2 disabled manual-review sources.
- Removed stale or unreliable pasted links: old World Bank Azerbaijan MPO direct PDF, old GRI 11 third-party PDF mirror, old Copernicus SciHub endpoint, Columbia SIPA PDF returning 502, As You Sow PDF timing out, and third-party SASB oil and gas services PDF returning 403.
- Replacements added: stable World Bank MPO Europe and Central Asia page, official GRI 11 sector-standard page, and current Copernicus Sentinel-1 Data Space page.
- Disabled for manual review: ResearchGate oil-pollution page and FERC environmental overview, both because they returned 403 during audit.
- Verification performed: Loaded `data/sources.csv` with `load_source_registry`; confirmed 37 enabled and 2 skipped/disabled sources.
- Next task: Milestone 4 discovery can now use `data/sources.csv` as its initial source registry.
