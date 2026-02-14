# Open-source GitHub ecosystem for a Labor Relations Research Platform

**The `labordata` GitHub organization is the single most valuable resource for this platform**, providing 27 actively maintained repositories that already aggregate NLRB, OSHA, WHD, OLMS, and FMCS data into a unified data warehouse with 40.5 million rows across 24 tables. Combined with mature tools like **edgartools** (1,400★) for SEC EDGAR, **Splink** (1,800★) for entity resolution, and **openFEC** (519★) for campaign finance — all with native or near-native PostgreSQL support — the open-source ecosystem covers every data source the platform needs. The only significant gap: **no projects exist for state PERB/labor board data**, representing a clear opportunity for original development.

---

## The labordata organization anchors the entire ecosystem

The **labordata** GitHub organization (https://github.com/labordata), created by Forest Gregg of DataMade, operates as a near-comprehensive labor data pipeline. Its 27 repositories cover NLRB cases, OLMS union filings, FMCS bargaining notices, OSHA enforcement, WHD compliance, and work stoppages — all updated nightly via GitHub Actions and served through a Datasette warehouse at labordata.bunkum.us. The `nlrb-data` repository already uses **PLpgSQL** and builds a PostgreSQL database directly, making it the most seamless integration target.

The highest-value labordata repositories are:

- **labordata/nlrb-data** (21★, updated Nov 2025) — Daily-refreshed NLRB representation certification and ULP cases since 2010, written in PLpgSQL with normalized tables for cases, participants, allegations, tallies, and elections. This is the foundation for any PostgreSQL-based NLRB integration.
- **labordata/nlrb-voluntary-recognitions** (12★) — FOIA-obtained voluntary recognition filings, filling a gap that standard NLRB election data misses entirely.
- **labordata/opdr** (3★, updated Aug 2025) — OLMS Online Public Disclosure Room database containing LM-2/LM-3/LM-4 union financial filings with membership counts, revenue, expenditures, and officer compensation.
- **labordata/fmcs-f7** (2★, updated Feb 8, 2026) — Daily-refreshed collective bargaining notices from FMCS, providing real-time visibility into active bargaining.
- **labordata/whd-compliance** (2★, updated Apr 2025) — WHD investigation data normalized into three tables: cases, violations, and FLSA details (minimum wage, overtime, retribution).
- **labordata/osha-enforcement** (updated Apr 2025) — OSHA enforcement data pipeline with Makefile-based ETL.
- **labordata/labor-union-parser** (updated Jan 2026) — Utility library to extract affiliation and identifier from union names, essential for cross-dataset entity resolution.
- **labordata/warehouse** (updated Jan 2026) — The Datasette-powered warehouse combining all datasets, providing a proven architectural reference.

Historical NLRB coverage extends back decades through **labordata/nlrb-cats** (2000–2010 case data), **labordata/CHIPS** (1984–2000), and **labordata/nlrb_old_rcases** (1965–1998 election results from AFL-CIO data). The **labordata/lm20** and **labordata/lm10** repositories uniquely track labor relations consultant (union avoidance) filings and employer financial dealings — data unavailable from any other open-source project.

---

## SEC EDGAR tools offer deep corporate data extraction

The SEC EDGAR ecosystem on GitHub is the most mature of any category, with multiple high-star, actively maintained projects. **edgartools** stands out as the comprehensive choice, while specialized tools address specific needs like XBRL parsing and 10-K section extraction.

**edgartools** (https://github.com/dgunning/edgartools, ~1,400★) is the most comprehensive SEC EDGAR library available. It parses all SEC form types, extracts XBRL financial statements into pandas DataFrames, and includes a built-in MCP server for AI integration. For labor research, it can extract **employee counts** via the XBRL tag `EntityNumberOfEmployees`, human capital disclosures from 10-K Item 1, and subsidiary data. Active development with 24 releases in 60 days makes it the clear first choice.

**sec-edgar-downloader** (https://github.com/jadchaar/sec-edgar-downloader, ~1,000★) handles bulk filing downloads with SEC-compliant rate limiting. Its companion **sec-edgar-api** wraps SEC's official REST API for company facts and concepts. **edgar-crawler** (https://github.com/lefterisloukas/edgar-crawler, ~500★, presented at WWW 2025) extracts specific text sections from 10-K, 10-Q, and 8-K filings into structured JSON — particularly valuable for Item 1 human capital disclosures, which became mandatory in November 2020.

For Exhibit 21 subsidiary parsing, **sec-api** (https://github.com/janlukasschroeder/sec-api, 247★) offers a dedicated Subsidiary API covering 100,000+ subsidiary lists since 2003, though it requires an API key. The older **CorpWatch API** (https://github.com/michalgm/corpwatchapi) pioneered Exhibit 21 parsing but has been unfunded since 2010. **bellingcat/EDGAR** (~300★) provides CLI-based full-text search with CSV export, built for investigative journalism.

For XBRL-specific parsing, **py-xbrl** (https://github.com/manusimidt/py-xbrl, ~132★) handles both XBRL and iXBRL files, while **django-sec** (https://github.com/chrisspen/django-sec) provides a Django app that stores XBRL attributes directly in SQL databases — natively supporting PostgreSQL as a backend.

A critical integration note: some XBRL filings include the `EntityTaxIdentificationNumber` tag, which is the **EIN** — enabling direct CIK-to-EIN matching between SEC and IRS databases without manual crosswalking.

---

## IRS Form 990 parsing is well-served by specialized tools

**IRSx / 990-xml-reader** (https://github.com/jsfenfen/990-xml-reader, 122★, updated Jun 2024) is the most comprehensive Python parser for IRS 990 XML data. It converts versioned XML returns into standardized Python objects, JSON, or CSV, preserving original line numbers. For labor research, the critical extractions are: **employee counts** (Part V), **executive compensation** (Schedule J), **officer/key employee data** (Part VII), and total compensation expense. A companion project provides database loading management commands.

**CharityNavigator/irs990** (~200★) takes an ETL approach using SQLAlchemy, processing 2.5 million electronic returns from AWS S3 into database tables — directly adaptable to PostgreSQL. The **Nonprofit-Open-Data-Collective's irs990efile** R package (v1.0.0, 2025) offers a complete data dictionary and concordance file mapping XML paths to rectangular database tables, making it the best reference for PostgreSQL schema design even if Python is the preferred language.

For lighter-weight access, **ProPublica's Nonprofit Explorer API** (wrapped by https://github.com/Punderthings/propublica990) provides pre-parsed 990 data by EIN, avoiding the complexity of raw XML processing.

---

## Entity matching libraries can scale to 100K employers

Matching employer names across NLRB, OSHA, SEC, BLS, DOL, and IRS databases is a core challenge. Three libraries stand out for production use with PostgreSQL.

**Splink** (https://github.com/moj-analytical-services/splink, ~1,800★) is the recommended primary engine. Built by the UK Ministry of Justice, it performs probabilistic record linkage using the Fellegi-Sunter model with **native PostgreSQL backend support** (`pip install splink[postgres]`). It links 1 million records on a laptop in approximately one minute, requires no training data (unsupervised), and has been proven at government scale — the Australian Bureau of Statistics used it for their National Linkage Spine. For employer matching, combining name + address + state + industry code yields the best results.

**dedupe** (https://github.com/dedupeio/dedupe, ~4,400★) uses active learning where domain experts label example pairs, and the system learns matching rules. It includes a dedicated PostgreSQL example (`pgsql_big_dedupe_example`) and has been used with campaign contribution databases containing millions of records. The **dchud/osha-dedupe** project demonstrates this approach specifically for OSHA inspection data in PostgreSQL.

**RapidFuzz** (https://github.com/rapidfuzz/RapidFuzz, ~3,700★) provides the string similarity scoring layer — Levenshtein, Jaro-Winkler, Damerau-Levenshtein — at 10–100x the speed of FuzzyWuzzy via a C++ core. For company names specifically, **name_matching** (https://github.com/DeNederlandscheBank/name_matching, ~160★) from the Dutch Central Bank was purpose-built for matching financial institution names across databases, with legal suffix handling and TF-IDF pre-filtering. **cleanco** (https://github.com/psolin/cleanco, ~340★) strips organizational type terms (Ltd, Corp, LLC) as an essential preprocessing step.

The recommended architecture layers these tools: cleanco for name standardization → Splink (PostgreSQL backend) for probabilistic matching → RapidFuzz for custom comparison functions → name_matching for validation.

---

## Government contract and BLS data fill employer profiles

**fedspendingtransparency/usaspending-api** (https://github.com/fedspendingtransparency/usaspending-api, 384★) is the official USASpending.gov API, already built on **PostgreSQL** with Django. It provides pg_restore-compatible database snapshots covering all federal contracts, grants, and financial assistance. This is the most PostgreSQL-ready project in the entire ecosystem — schemas, materialized views, and Django migrations can be directly replicated.

For FPDS procurement data, **dherincx92/fpds** (https://github.com/dherincx92/fpds, 33★, updated Jul 2025) parses FPDS ATOM feeds with async support and ~85% speed improvement in recent versions. **makegov/procurement-tools** provides SAM.gov entity data retrieval with Pydantic models, and their **awesome-procurement-data** list curates all federal procurement APIs and tools.

For BLS data, **OliverSherouse/bls** (https://github.com/OliverSherouse/bls, 84★) wraps the BLS API returning pandas-compatible data for any series. The specialized **TrentLThompson/qcew** package retrieves QCEW data by FIPS code, NAICS industry, and establishment size — critical for employment/wage analysis at the geographic level. **armollica/qcew-data** (https://github.com/armollica/qcew-data) goes further by bulk-loading 25 years of QCEW CSVs (~36.4 GB) directly into PostgreSQL via SQLAlchemy.

---

## Campaign finance and news monitoring enable event tracking

**fecgov/openFEC** (https://github.com/fecgov/openFEC, 519★) is the official FEC API, built on **PostgreSQL** with Flask/SQLAlchemy and nightly materialized view refreshes. It covers all contribution receipts (Schedule A), disbursements (Schedule B), and independent expenditures. For linking corporate political spending to employers, **OpenSecrets API** wrappers like **robrem/opensecrets-crpapi** provide industry contribution data and PAC summaries.

For raw FEC filing parsing, **esonderegger/fecfile** (https://github.com/esonderegger/fecfile, 46★) converts .fec format files into native Python objects, handling all 47+ form types and schedules. **LindsayYoung/campaign-finance-guide** provides essential context for designing campaign finance database schemas.

News monitoring for labor events relies on two complementary approaches. **GDELT** access via **alex9smith/gdelt-doc-api** (https://github.com/alex9smith/gdelt-doc-api, 172★) enables keyword-based article search with timeline analysis — searching for terms like "strike," "union vote," "walkout" across global news updated every 15 minutes. **newsapi-python** (https://github.com/mattlisiv/newsapi-python, 482★) wraps NewsAPI.org for headline and archive searching across thousands of sources. Both return pandas DataFrames directly loadable into PostgreSQL.

The **Cornell ILR Labor Action Tracker** (https://striketracker.ilr.cornell.edu/) — while not a GitHub project per se — is the premier manually curated database of U.S. strikes and labor protests since 2021, with its source repo at **ilrWebServices/StrikeSiteTracker**. It captures events BLS misses (stoppages under 1,000 workers) and includes employer, union, industry, location, duration, and demand variables.

---

## Census and geographic tools round out the data infrastructure

**datamade/census** (https://github.com/datamade/census, 677★) is the most mature Census API wrapper, supporting ACS 1-year, 3-year, and 5-year data through 2023 across all standard geographies. **censusdis** (https://github.com/censusdis/censusdis, presented at SciPy '24) is the most modern option with automatic metadata discovery and GeoPandas geometry support for PostGIS integration. **cenpy** (https://github.com/cenpy-devs/cenpy, 191★) adds TIGER Web Mapping Service integration for geographic boundary data.

These tools build the geographic dimension tables — FIPS-coded states, counties, MSAs/CBSAs — that serve as join keys across QCEW, OSHA, NLRB, and WHD data.

---

## What doesn't exist yet: gaps and opportunities

Three significant gaps emerged from this research:

**State PERB/labor board data** has zero open-source coverage on GitHub. No scrapers or datasets exist for California PERB, New York PERB, Illinois ILRB, or any other state public employment relations board. Building these would be a unique contribution to the ecosystem.

**No "awesome-labor" curated list** exists, despite the breadth of labor-adjacent open-source tools. Creating one would benefit the broader labor data community.

**No unified PostgreSQL-based labor research platform** exists as open source. The labordata warehouse uses SQLite/Datasette, and no project combines a FastAPI backend with PostgreSQL for multi-source labor data. The platform described in this query would be genuinely novel.

---

## Recommended integration priority for the platform

| Priority | Project | Stars | PostgreSQL fit | Data source |
|----------|---------|-------|---------------|-------------|
| 1 | labordata/nlrb-data | 21 | Native PLpgSQL | NLRB |
| 2 | labordata/whd-compliance | 2 | Direct import | DOL/WHD |
| 3 | labordata/osha-enforcement | 0 | Direct import | OSHA |
| 4 | labordata/opdr | 3 | Direct import | OLMS |
| 5 | labordata/fmcs-f7 | 2 | Direct import | FMCS |
| 6 | Splink | 1,800 | Native backend | Entity matching |
| 7 | edgartools | 1,400 | Via DataFrames | SEC EDGAR |
| 8 | IRSx (990-xml-reader) | 122 | Via JSON/CSV | IRS 990 |
| 9 | usaspending-api | 384 | Native PostgreSQL | Gov contracts |
| 10 | openFEC | 519 | Native PostgreSQL | FEC/PAC |
| 11 | datamade/census | 677 | Via DataFrames | Census/ACS |
| 12 | armollica/qcew-data | — | Native PostgreSQL | BLS QCEW |
| 13 | gdelt-doc-api | 172 | Via DataFrames | News monitoring |
| 14 | labordata/labor-union-parser | 0 | Python utility | Union name resolution |
| 15 | cleanco + name_matching | 340+160 | Python utility | Name standardization |

## Conclusion

The open-source ecosystem for labor data is deeper and more active than might be expected, but it is fragmented. The **labordata organization** has done the hardest work — building and maintaining nightly ETL pipelines for the most critical government data sources — yet it remains a collection of small repositories rather than a unified platform. The entity matching tools (**Splink**, **dedupe**) and corporate data tools (**edgartools**, **openFEC**, **usaspending-api**) are individually excellent and production-ready, but no project has yet connected them into an integrated research system. A PostgreSQL-based platform with FastAPI that unifies these 15+ data sources, applies entity resolution across ~100K employers using Splink's native PostgreSQL backend, and links NLRB election outcomes to SEC disclosures, OSHA violations, WHD enforcement, and political spending would be the first of its kind. The infrastructure exists in pieces; the integration work is the novel contribution.