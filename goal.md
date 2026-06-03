# AI Operating Brief: Commercial Energy Intelligence Webcrawler

## 1. Assignment Positioning

Build a small, modular webcrawler proof of concept that could mature into a commercial public-source intelligence product for large energy companies such as ExxonMobil.

The demonstration case is the Azerbaijani oil and gas sector. Azerbaijan is useful because it combines energy infrastructure, international operators, Caspian environmental concerns, state-linked information channels, transparency debates, and geopolitical sensitivity. The crawler should show how a company could monitor a difficult operating environment using public, legally accessible sources.

This is not only an academic literature crawler and not a generic news scraper. It is a defensible prototype for a sellable system that gathers, cleans, validates, and summarizes external signals for energy-sector decision makers.

## 2. Why This Should Interest CYNICS Researchers

The assignment should connect commercial web crawling to research themes visible in the CYNICS publication record, especially work by Arvind Sundaram and Hany S. Abdel-Khalik.

Relevant research themes:

- Data trustworthiness in high-valued systems.
- Detection of subtle anomalies and adversarial process variations.
- Deceptive or manipulated data streams.
- Model-based signatures and cyber-physical system monitoring.
- Uncertainty quantification and validation of imperfect evidence.
- Operational resilience for industrial systems.

The research hook is:

**How can an energy company trust external public data streams when sources are incomplete, biased, noisy, stale, or potentially manipulated?**

The crawler should therefore do more than collect documents. It should attach provenance, compare conflicting sources, flag uncertainty, detect changes over time, and preserve enough evidence for cited analysis.

## 3. Target Customer And Value Proposition

Assume the eventual buyer is a major energy company evaluating or monitoring overseas assets.

The product should help answer questions such as:

- What public sources mention specific assets, pipelines, fields, operators, or extraction sites?
- What environmental, public-health, labor, corruption, sanctions, or community-risk issues are being reported?
- Which claims are supported by multiple independent sources?
- Which claims come only from official, corporate, activist, or state-linked sources?
- What changed since the last monitoring cycle?
- Where are there anomalies, contradictions, or missing data?
- What evidence should an analyst read before making a business, safety, or compliance recommendation?

The commercial value is not "scraping websites." The value is a repeatable pipeline for trustworthy, cited, risk-aware energy intelligence.

## 4. Azerbaijan Demonstration Scope

Use Azerbaijan as the first case study, with focus on the oil and gas sector and public sources from roughly 2024-2026.

Primary topics:

- Oil and gas assets, fields, pipelines, terminals, operators, and major projects.
- Transparency, governance, contract, revenue, and corruption-risk reporting.
- Environmental impact, Caspian Sea ecology, emissions, spills, and public-health claims.
- Community, labor, and human-rights reporting connected to energy operations.
- Energy-market, export, sanctions, and geopolitical context.
- Public cyber, operational technology, and critical-infrastructure risk context when available from responsible sources.

The crawler should avoid private, classified, or intrusive data. It should demonstrate how to build intelligence from open sources only.

## 5. Source Strategy

Prioritize sources that an enterprise customer could defend in a due-diligence workflow. Record provenance for every document: source name, URL, publisher, date, retrieval date, access method, source tier, and notes.

### Tier 1: Multilateral And International Organizations

Use these for baseline data, governance indicators, development context, and macroeconomic framing.

- World Bank.
- EITI.
- UNDP.
- IMF.
- IEA.
- OECD, when relevant.

### Tier 2: Corporate, Operator, And Government Sources

Use these for official positions, asset names, timelines, investment claims, and operating context. Label them as stakeholder sources.

- SOCAR.
- BP Azerbaijan.
- ExxonMobil and other major operators or partners when relevant.
- Azerbaijan ministries and regulators.
- Company sustainability, annual, and investor reports.

### Tier 3: Human Rights, Environmental, And Transparency Organizations

Use these for risk claims, investigations, and issues not always visible in official sources.

- Human Rights Watch.
- Global Witness.
- Amnesty International.
- Publish What You Pay.
- International Crisis Group, when relevant.

### Tier 4: Academic And Scientific Sources

Use these for environmental, public-health, and technical evidence.

- Google Scholar discovery followed by legal publisher or repository access.
- Crossref, OpenAlex, and Semantic Scholar metadata.
- University repositories.
- Open-access journals and preprint servers.
- Caspian Sea ecology and energy-impact studies.

### Tier 5: Critical Infrastructure And Cyber Context

Use these only for defensive, high-level operational risk context.

- CISA ICS advisories.
- MITRE ATT&CK for ICS.
- NIST cybersecurity publications.
- Public reports on energy-sector cyber risk.

Do not collect exploit code, credentials, facility-sensitive details, or instructions for attacking live systems.

## 6. Safety, Ethics, And Legal Constraints

This project must be safe enough to show to a university researcher or corporate compliance team.

Non-negotiable rules:

- Use only public, legally accessible material.
- Respect `robots.txt`, terms of service, API policies, sitemaps, and rate limits.
- Prefer official APIs, RSS feeds, sitemaps, public datasets, and metadata services before scraping HTML.
- Do not bypass paywalls, logins, CAPTCHA, anti-bot systems, or access controls.
- Do not automate vulnerability probing against live industrial systems.
- Do not collect private social media content, personal accounts, credentials, or sensitive facility details.
- Do not store unnecessary personally identifiable information.
- Redact PII before persistent storage when names, addresses, phone numbers, emails, precise personal locations, or personal identifiers are not analytically required.
- Prefer storing metadata, cleaned excerpts, embeddings, and derived insights instead of full raw HTML or full raw PDFs.
- If raw files are needed for debugging, keep them in a clearly marked temporary cache and document how to delete them.
- Make uncertainty visible. Do not present legal, political, health, environmental, safety, or security claims as fact unless the source is cited and confidence is stated.

## 7. Target Architecture

Build a modular, RAG-ready pipeline:

1. **Source registry:** A CSV, YAML, or SQLite table listing source name, tier, base URL, allowed access method, rate limit, and notes.
2. **Discovery:** Locate reports, pages, PDFs, datasets, advisories, and metadata using APIs, sitemaps, RSS feeds, search pages, or manual seed URLs.
3. **Ingestion:** Fetch a small number of selected pages or documents with polite headers, timeouts, retries, logging, and rate limiting.
4. **Extraction:** Convert HTML and PDFs into structured text or Markdown with source metadata attached.
5. **Cleaning:** Remove navigation clutter, boilerplate, duplicate text, tracking fragments, and irrelevant page chrome.
6. **Redaction:** Detect and redact unnecessary PII before long-term storage.
7. **Entity extraction:** Identify companies, assets, fields, pipelines, locations, organizations, dates, risk topics, and claim types.
8. **Trust scoring:** Attach simple, explainable confidence fields such as source tier, independence, freshness, corroboration count, and conflict flags.
9. **Storage:** Save metadata and cleaned text in a simple local store first, such as CSV, JSONL, or SQLite.
10. **Retrieval:** Add embeddings or a vector database only after the cleaned corpus is trustworthy.
11. **Analysis:** Generate cited summaries, risk notes, source comparisons, timelines, and change reports.

Start simple. A notebook, CSV files, and SQLite are acceptable for the proof of concept. Cloud warehouses, dashboards, and production APIs should wait until the data model and ingestion workflow are proven.

## 8. Product Features To Demonstrate

The proof of concept should demonstrate a path to a commercial product:

- **Source coverage map:** What sources are monitored, how often, and why they matter.
- **Asset and topic tracker:** Mentions of companies, assets, fields, pipelines, and risk categories.
- **Evidence ledger:** Every answer links back to source URLs and retrieval metadata.
- **Contradiction detection:** Claims that differ across official, NGO, academic, and corporate sources.
- **Freshness monitoring:** Newly published or changed pages and reports.
- **Confidence scoring:** A simple explanation of how trustworthy each claim appears.
- **Analyst-ready export:** CSV, Markdown, or notebook output that a business or compliance analyst can inspect.

## 9. Research Questions The Pipeline Should Support

The assignment should produce artifacts that connect commercial intelligence to CYNICS-style research:

- How can provenance and corroboration act as "data trustworthiness signatures" for open-source intelligence?
- Can the crawler detect subtle changes in public reporting that may signal operational, environmental, or reputational risk?
- How should uncertainty be represented when sources conflict or when only stakeholder sources are available?
- What features distinguish high-quality evidence from noisy, repetitive, or biased web content?
- How could a company validate a crawler's outputs before using them in strategic decisions?
- What parts of the pipeline could generalize from Azerbaijan to other energy-producing regions?

## 10. Implementation Guidance For AI Assistants

When asked to build or modify this project, follow this response pattern:

1. State the immediate goal in one sentence.
2. Explain the data engineering or analytics concept being practiced.
3. Identify the file or module being changed.
4. Provide a small implementation.
5. Show how to run it.
6. Show what successful output should look like.
7. Name the next logical module.

Code standards:

- Use Python unless there is a clear reason to use another language.
- Keep modules focused: one responsibility per file.
- Include `timeout`, `User-Agent`, and basic error handling in network code.
- Log what was fetched, skipped, parsed, redacted, and stored.
- Add rate limiting for all scraping and API calls.
- Make functions testable without live network calls where practical.
- Store seed URLs, source tiers, search terms, and rate limits outside the code when the project grows.
- Avoid 100-line all-in-one scripts. Split discovery, fetching, extraction, cleaning, redaction, entity extraction, trust scoring, and storage.

Recommended early libraries:

- `requests` or `httpx` for HTTP.
- `beautifulsoup4` for HTML parsing.
- `trafilatura` or `readability-lxml` for article text extraction.
- `pymupdf` or `pdfplumber` for PDFs.
- `pandas` for tabular registries.
- `sqlite3` for local structured storage.
- `rapidfuzz` for deduplicating titles, URLs, and organization names.
- `re` plus a later NLP library for redaction and entity extraction.

## 11. First Proof-Of-Concept Milestones

Build in this order:

1. **Source registry:** Create `data/sources.csv` with source name, tier, base URL, allowed access method, notes, and last checked date.
2. **Robots checker:** Create a script that checks `robots.txt` and prints whether a target path is allowed.
3. **Seed discovery:** Extract a small list of candidate URLs from one Tier 1 source and one stakeholder source.
4. **Single-page fetcher:** Fetch one permitted page with polite headers and save metadata plus HTML to a temporary folder.
5. **HTML-to-Markdown cleaner:** Extract the main text and remove navigation clutter.
6. **PDF extractor:** Download or read one public report PDF and extract page-level text.
7. **PII redactor:** Redact emails, phone numbers, and obvious personal identifiers before storage.
8. **Entity tagger:** Tag companies, assets, locations, dates, and risk topics.
9. **Trust-score prototype:** Add source tier, freshness, corroboration count, and conflict flag fields.
10. **SQLite or JSONL store:** Save cleaned documents and extracted claims with provenance fields.
11. **Mini analyst report:** Produce one cited Azerbaijan energy-sector brief from 8-12 sources.
12. **Optional RAG layer:** Add embeddings only after the metadata, cleaning, and trust fields are reliable.

## 12. Source Evaluation Template

Use this format when adding a source:

- **Source name:**
- **URL:**
- **Tier:**
- **Publisher type:** Multilateral, company, government, NGO, academic, security advisory, media, or other.
- **Relevant topic:**
- **Access method:** API, sitemap, RSS, public HTML, public PDF, or manual download.
- **Robots or terms notes:**
- **Expected document types:**
- **Known bias or limitation:**
- **Fields to capture:**

## 13. Claim Evaluation Template

Use this format when extracting a claim:

- **Claim:**
- **Source URL:**
- **Publisher:**
- **Publication date:**
- **Retrieval date:**
- **Companies or assets mentioned:**
- **Location:**
- **Risk category:** Market, environmental, public health, governance, labor, human rights, cyber, operational, or other.
- **Evidence excerpt:**
- **Corroborating sources:**
- **Conflicting sources:**
- **Confidence level:**
- **Analyst notes:**

## 14. Analysis Output Template

Use this format for analytical results:

- **Question answered:**
- **Sources used:**
- **Date range covered:**
- **Key findings:**
- **Asset or topic map:**
- **Source agreement and disagreement:**
- **Confidence level:**
- **Known gaps:**
- **Recommended next sources:**

## 15. Hera Reference

Hera (https://devpost.com/software/hera-9sub6t) is useful as inspiration for multi-source corporate intelligence: gather documents from several public repositories, organize them into a data store, and generate summaries, timelines, scores, and pattern analyses.

Do not copy Hera's architecture blindly. For this project, the correct first version is smaller:

- Local files before cloud warehouses.
- CSV or SQLite before Snowflake.
- Manual review before automated scoring.
- Cited summaries before dashboards.
- Ethical safeguards before scale.
- Trustworthy provenance before polished product claims.
