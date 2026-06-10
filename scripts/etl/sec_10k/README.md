# SEC 10-K text-mining foundation

Two-step ETL that produces a local mirror of recent 10-K filings for the
top ~1,500 SEC issuers we have linked to a master employer. Output is the
input for downstream Q16 (Suppliers), Q17 (Distribution), and Q19
(Customers) text-mining jobs.

## Files

| Script | What it does |
|---|---|
| `identify_recent_10k.py` | Picks the top-N SEC filers (ranked by master + employee count), queries EDGAR submissions JSON for each one, and upserts the most recent 10-K (or 10-K/A) into `sec_10k_filings_to_download`. |
| `download_10k_batch.py`  | Reads the queue, fetches the primary 10-K HTML to `files/sec_10k/{cik}/{accession}.html`, writes status to `load_sec_10k_progress`. Resumable: existing files are detected and skipped. |

## Tables

`sec_10k_filings_to_download` (PK `(cik, accession)`)

| Column | Notes |
|---|---|
| `cik` | SEC central index key (BIGINT). |
| `accession` | 18-digit accession with dashes stripped (the filename used in EDGAR archive paths). |
| `accession_dashed` | Same accession with the `xxxxxxxxxx-yy-zzzzzz` formatting. |
| `primary_document` | Filename of the 10-K body inside the filing bundle (often null for older filings). |
| `filing_date` / `report_date` | Calendar dates. |
| `form` | `10-K` or `10-K/A`. `NONE` is a sentinel for "no 10-K on file" (kept so re-runs are idempotent). |
| `company_name` / `ticker` / `master_id` | Denormalized for diagnostic queries. |
| `rank_score` | The employee-count number used to pick this filer. |
| `rank_position` | 1-based position in the top-N pull. |

`load_sec_10k_progress` (PK `(cik, accession)`)

Mirrors the `load_def14a_progress` pattern. Statuses:

* `pending` -- queued but not yet downloaded.
* `downloaded` -- file is on disk.
* `cached` -- a re-run found the file already on disk and didn't re-fetch.
* `http_error` -- both the primary-document URL and the index-scan
  fallback returned nothing.
* `no_doc` / `parse_error` -- failures during the fallback path.

## Invocation

```powershell
# Smoke-test (5 candidates, populates queue + progress):
py scripts/etl/sec_10k/identify_recent_10k.py --limit 5

# Production identify run -- ~5 minutes at 5 req/sec:
py scripts/etl/sec_10k/identify_recent_10k.py --limit 1500

# Smoke-test the downloader (5 random pending rows, ~5-15 MB each):
py scripts/etl/sec_10k/download_10k_batch.py --limit 5

# Drain the entire queue:
py scripts/etl/sec_10k/download_10k_batch.py
```

Verification one-liners:

```sql
SELECT COUNT(*) FROM sec_10k_filings_to_download;
SELECT status, COUNT(*) FROM load_sec_10k_progress GROUP BY status;
SELECT pg_size_pretty(SUM(bytes_written)) AS bytes_on_disk
  FROM load_sec_10k_progress
 WHERE status = 'downloaded';
```

## Rate limit

Both scripts cap themselves at 5 requests / second per CLAUDE.md SEC
fair-use convention (their published ceiling is 10/s). User-Agent defaults
to `LaborDataPlatform/1.0 (jakewartel@gmail.com)`; override with the
`SEC_USER_AGENT` env var.

## Resumability

* `identify_recent_10k.py` is idempotent: re-running upserts existing rows
  via `ON CONFLICT DO UPDATE`.
* `download_10k_batch.py` skips rows already at status `downloaded` /
  `verified`. Use `--retry-failed` to re-attempt rows that errored.

## What this enables

Once a 10-K is on disk you can grep / parse the standard 10-K item
boundaries:

* **Item 1 / 1A** -- "Business" + "Risk Factors" -- top customers,
  competition, regulatory landscape (Q14/Q15/Q19).
* **Item 1** sub-section "Suppliers" / "Raw Materials" (Q16).
* **Item 1** sub-section "Distribution" / "Sales and Marketing" (Q17).
* **Item 21 / Exhibit 21** is already covered by `load_sec_exhibit21.py`;
  this scaffolding does **not** re-fetch it.

## Reference loaders

* `scripts/etl/load_def14a_directors.py` -- DEF14A proxy text-mining.
  Same EDGAR client + progress-table pattern.
* `scripts/etl/load_sec_exhibit21.py` -- pulls Exhibit 21 from the same
  10-K filings; we do **not** duplicate that.
