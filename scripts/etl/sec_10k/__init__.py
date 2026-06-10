"""SEC 10-K text-mining foundation (Q16 Suppliers / Q17 Distribution / Q19 Customers).

Two-stage pipeline:
  1. ``identify_recent_10k`` -- pick the top ~1,500 SEC filers (ranked by
     master coverage + employee count) and resolve their most recent 10-K
     filing via SEC EDGAR submissions JSON; populate
     ``sec_10k_filings_to_download``.
  2. ``download_10k_batch`` -- fetch the primary 10-K HTML document for each
     queued row, write to ``files/sec_10k/{cik}/{accession}.html``, and
     mirror progress in ``load_sec_10k_progress``.

Both stages mirror the rate-limiting + per-filer pipeline pattern used by
``scripts/etl/load_def14a_directors.py`` and ``scripts/etl/load_sec_exhibit21.py``.
"""
