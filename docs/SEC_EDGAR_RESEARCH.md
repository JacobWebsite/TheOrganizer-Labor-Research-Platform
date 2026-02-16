# SEC EDGAR Research (Phase 4 Block A, ETL Scope)

Date: 2026-02-16

## Findings

1. Full company coverage is available from SEC bulk submissions data.
- The SEC bulk file `submissions.zip` contains company-level JSON documents for the full EDGAR filer universe (hundreds of thousands of entities).
- This is a better fit for one-pass ETL than iterating individual entities through client APIs.

2. edgartools is useful for entity-level exploration, but bulk ETL is more direct via SEC bulk files.
- For full-load ETL, parsing `submissions.zip` is simpler and faster than per-company API calls.
- edgartools can still be used later for targeted enrichment (for example, filing-specific extraction).

3. Metadata available directly in submissions records:
- `cik` (SEC identifier)
- `name` (company name)
- `ein` (present for some entities)
- `sic` (industry code)
- `addresses.business` and `addresses.mailing` (contains state/city/street metadata)
- `filings.recent.filingDate` (recent filing date array)

4. EIN extraction strategy:
- In this ETL phase, EIN is taken from submissions metadata when present.
- XBRL extraction for `dei:EntityTaxIdentificationNumber` is possible but is deferred because it is slower and requires per-filing processing.

5. Rate limit and operational considerations:
- SEC guidance commonly references responsible usage around 10 requests/second and a valid `User-Agent`.
- Bulk download + local processing reduces request volume and avoids per-company throttling risk.

## Implementation Decision

Use `submissions.zip` as the canonical ETL source for `sec_companies`, with:
- local zip path support
- optional download if missing
- idempotent UPSERT loading
- indexes for downstream matching.
