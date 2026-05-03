"""
Load FEC bulk campaign finance data for the 2023-2024 cycle.

24Q-38 Political (Q24). Loads four FEC bulk files into Postgres:
  - cm24.zip    -> fec_committees             (~25K rows)
  - cn24.zip    -> fec_candidates             (~5K rows)
  - indiv24.zip -> fec_individual_contributions (millions of rows; key for matching)
  - pas224.zip  -> fec_committee_contributions  (~500K rows; PAC -> candidate flows)

The EMPLOYER column on indiv contributions is the matching key to
master_employers (most donors list their employer for the FEC). The
CONNECTED_ORG_NM column on cm is the matching key for corporate PACs
(every "Walmart PAC" lists Walmart as its connected org).

Source: https://www.fec.gov/data/browse-data/?tab=bulk-data
Schema: https://www.fec.gov/campaign-finance-data/contributions-individuals-file-description/

Usage:
    py scripts/etl/load_fec.py                            # use existing zips
    py scripts/etl/load_fec.py --redownload               # re-fetch from FEC
    py scripts/etl/load_fec.py --skip-indiv               # load everything except indiv (fast pass)

Indexes deferred until after load (mirrors load_epa_echo.py pattern).
"""
import argparse
import csv
import io
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection

FEC_DIR = PROJECT_ROOT / "files" / "fec"
URLS = {
    "cm24.zip":      "https://www.fec.gov/files/bulk-downloads/2024/cm24.zip",
    "cn24.zip":      "https://www.fec.gov/files/bulk-downloads/2024/cn24.zip",
    "indiv24.zip":   "https://www.fec.gov/files/bulk-downloads/2024/indiv24.zip",
    "pas224.zip":    "https://www.fec.gov/files/bulk-downloads/2024/pas224.zip",
}

# ---------------------------------------------------------------------------
# Schemas (column order MUST match FEC spec exactly)
# ---------------------------------------------------------------------------

CM_COLS = [
    "cmte_id", "cmte_nm", "tres_nm", "cmte_st1", "cmte_st2", "cmte_city",
    "cmte_st", "cmte_zip", "cmte_dsgn", "cmte_tp", "cmte_pty_affiliation",
    "cmte_filing_freq", "org_tp", "connected_org_nm", "cand_id",
]

CN_COLS = [
    "cand_id", "cand_name", "cand_pty_affiliation", "cand_election_yr",
    "cand_office_st", "cand_office", "cand_office_district", "cand_ici",
    "cand_status", "cand_pcc", "cand_st1", "cand_st2", "cand_city",
    "cand_st", "cand_zip",
]

INDIV_COLS = [
    "cmte_id", "amndt_ind", "rpt_tp", "transaction_pgi", "image_num",
    "transaction_tp", "entity_tp", "name", "city", "state", "zip_code",
    "employer", "occupation", "transaction_dt", "transaction_amt",
    "other_id", "tran_id", "file_num", "memo_cd", "memo_text", "sub_id",
]

PAS2_COLS = [
    "cmte_id", "amndt_ind", "rpt_tp", "transaction_pgi", "image_num",
    "transaction_tp", "entity_tp", "name", "city", "state", "zip_code",
    "employer", "occupation", "transaction_dt", "transaction_amt",
    "other_id", "cand_id", "tran_id", "file_num", "memo_cd", "memo_text",
    "sub_id",
]

# ---------------------------------------------------------------------------
# DDL (table-only; indexes added after load)
# ---------------------------------------------------------------------------

DDL_TABLES = """
DROP TABLE IF EXISTS fec_committees CASCADE;
CREATE TABLE fec_committees (
    cmte_id              VARCHAR(9) PRIMARY KEY,
    cmte_nm              TEXT,
    tres_nm              TEXT,
    cmte_st1             TEXT,
    cmte_st2             TEXT,
    cmte_city            TEXT,
    cmte_st              CHAR(2),
    cmte_zip             VARCHAR(10),
    cmte_dsgn            CHAR(1),
    cmte_tp              CHAR(1),
    cmte_pty_affiliation VARCHAR(3),
    cmte_filing_freq     CHAR(1),
    org_tp               CHAR(1),
    connected_org_nm     TEXT,
    cand_id              VARCHAR(9),
    name_norm            TEXT,
    connected_org_norm   TEXT,
    loaded_at            TIMESTAMPTZ DEFAULT NOW()
);

DROP TABLE IF EXISTS fec_candidates CASCADE;
CREATE TABLE fec_candidates (
    cand_id              VARCHAR(9) PRIMARY KEY,
    cand_name            TEXT,
    cand_pty_affiliation VARCHAR(3),
    cand_election_yr     INTEGER,
    cand_office_st       CHAR(2),
    cand_office          CHAR(1),
    cand_office_district VARCHAR(2),
    cand_ici             CHAR(1),
    cand_status          CHAR(1),
    cand_pcc             VARCHAR(9),
    cand_st1             TEXT,
    cand_st2             TEXT,
    cand_city            TEXT,
    cand_st              CHAR(2),
    cand_zip             VARCHAR(10),
    loaded_at            TIMESTAMPTZ DEFAULT NOW()
);

DROP TABLE IF EXISTS fec_individual_contributions CASCADE;
CREATE TABLE fec_individual_contributions (
    sub_id               BIGINT PRIMARY KEY,
    cmte_id              VARCHAR(9),
    amndt_ind            CHAR(1),
    rpt_tp               VARCHAR(3),
    transaction_pgi      VARCHAR(5),
    image_num            VARCHAR(20),
    transaction_tp       VARCHAR(3),
    entity_tp            VARCHAR(3),
    name                 TEXT,
    city                 TEXT,
    state                CHAR(2),
    zip_code             VARCHAR(10),
    employer             TEXT,
    occupation           TEXT,
    transaction_dt       DATE,
    transaction_amt      NUMERIC(14,2),
    other_id             VARCHAR(9),
    tran_id              VARCHAR(40),
    file_num             BIGINT,
    memo_cd              CHAR(1),
    memo_text            TEXT,
    employer_norm        TEXT,
    loaded_at            TIMESTAMPTZ DEFAULT NOW()
);

DROP TABLE IF EXISTS fec_committee_contributions CASCADE;
CREATE TABLE fec_committee_contributions (
    sub_id               BIGINT PRIMARY KEY,
    cmte_id              VARCHAR(9),
    amndt_ind            CHAR(1),
    rpt_tp               VARCHAR(3),
    transaction_pgi      VARCHAR(5),
    image_num            VARCHAR(20),
    transaction_tp       VARCHAR(3),
    entity_tp            VARCHAR(3),
    name                 TEXT,
    city                 TEXT,
    state                CHAR(2),
    zip_code             VARCHAR(10),
    employer             TEXT,
    occupation           TEXT,
    transaction_dt       DATE,
    transaction_amt      NUMERIC(14,2),
    other_id             VARCHAR(9),
    cand_id              VARCHAR(9),
    tran_id              VARCHAR(40),
    file_num             BIGINT,
    memo_cd              CHAR(1),
    memo_text            TEXT,
    loaded_at            TIMESTAMPTZ DEFAULT NOW()
);
"""

DDL_INDEXES = """
CREATE INDEX idx_fec_cm_connected_org_norm ON fec_committees (connected_org_norm) WHERE connected_org_norm IS NOT NULL;
CREATE INDEX idx_fec_cm_state              ON fec_committees (cmte_st);
CREATE INDEX idx_fec_cm_type               ON fec_committees (cmte_tp);

CREATE INDEX idx_fec_indiv_employer_norm   ON fec_individual_contributions (employer_norm) WHERE employer_norm IS NOT NULL;
CREATE INDEX idx_fec_indiv_state           ON fec_individual_contributions (state);
CREATE INDEX idx_fec_indiv_cmte            ON fec_individual_contributions (cmte_id);
CREATE INDEX idx_fec_indiv_dt              ON fec_individual_contributions (transaction_dt);

CREATE INDEX idx_fec_paccontrib_cmte       ON fec_committee_contributions (cmte_id);
CREATE INDEX idx_fec_paccontrib_cand       ON fec_committee_contributions (cand_id);

CREATE INDEX idx_fec_cn_party              ON fec_candidates (cand_pty_affiliation);
"""


# ---------------------------------------------------------------------------
# Type coercion helpers
# ---------------------------------------------------------------------------

def _norm_int(v):
    if not v:
        return None
    try:
        return int(v)
    except (ValueError, TypeError):
        return None


def _norm_decimal(v):
    if not v:
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _norm_date(v):
    """FEC dates are MMDDYYYY string."""
    if not v or len(v) != 8:
        return None
    try:
        return datetime.strptime(v, "%m%d%Y").date()
    except (ValueError, TypeError):
        return None


def _norm_state(v):
    if not v:
        return None
    s = v.strip().upper()[:2]
    return s if len(s) == 2 and s.isalpha() else None


def _truncate(v, n):
    if v is None:
        return None
    s = str(v).strip()
    return s[:n] if s else None


def _norm_employer(name):
    """Aggressive normalization for employer matching."""
    if not name:
        return None
    s = name.upper().strip()
    if s in ("", "NONE", "N/A", "SELF", "SELF-EMPLOYED", "SELF EMPLOYED",
             "RETIRED", "NOT EMPLOYED", "UNEMPLOYED", "INFORMATION REQUESTED",
             "REQUESTED", "INFORMATION REQUESTED PER BEST EFFORTS"):
        return None
    for suffix in (" LLC", " L.L.C.", " INC", " INC.", " CORPORATION", " CORP",
                   " CO.", " COMPANY", " LP", " LTD", " PLLC", " PC"):
        if s.endswith(suffix):
            s = s[:-len(suffix)].rstrip(" ,.")
            break
    import re
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


# ---------------------------------------------------------------------------
# Generic row-streaming loader
# ---------------------------------------------------------------------------

def _stream_rows(zip_path: Path):
    """Yield list-of-strings rows from the single .txt inside a FEC zip.
    FEC files are pipe-delimited (`|`) with no header and CR/LF agnostic."""
    z = zipfile.ZipFile(zip_path)
    txt_name = next(n for n in z.namelist() if n.endswith(".txt"))
    with z.open(txt_name) as raw:
        text = io.TextIOWrapper(raw, encoding="utf-8", errors="replace", newline="")
        reader = csv.reader(text, delimiter="|", quoting=csv.QUOTE_NONE)
        for row in reader:
            yield row


def _load_committees(cur, conn):
    from psycopg2.extras import execute_values
    print("Loading fec_committees from cm24.zip...")
    t0 = time.time()
    BATCH = 5000
    sql = """
        INSERT INTO fec_committees (
            cmte_id, cmte_nm, tres_nm, cmte_st1, cmte_st2, cmte_city,
            cmte_st, cmte_zip, cmte_dsgn, cmte_tp, cmte_pty_affiliation,
            cmte_filing_freq, org_tp, connected_org_nm, cand_id,
            name_norm, connected_org_norm
        ) VALUES %s
        ON CONFLICT (cmte_id) DO NOTHING
    """
    batch, total, skipped = [], 0, 0
    for r in _stream_rows(FEC_DIR / "cm24.zip"):
        if len(r) < 15 or not r[0]:
            skipped += 1
            continue
        batch.append((
            _truncate(r[0], 9),
            _truncate(r[1], 200),
            _truncate(r[2], 90),
            _truncate(r[3], 34),
            _truncate(r[4], 34),
            _truncate(r[5], 30),
            _norm_state(r[6]),
            _truncate(r[7], 9),
            _truncate(r[8], 1),
            _truncate(r[9], 1),
            _truncate(r[10], 3),
            _truncate(r[11], 1),
            _truncate(r[12], 1),
            _truncate(r[13], 200),
            _truncate(r[14], 9),
            _norm_employer(r[1]),
            _norm_employer(r[13]),
        ))
        if len(batch) >= BATCH:
            execute_values(cur, sql, batch, page_size=BATCH)
            total += len(batch)
            batch = []
    if batch:
        execute_values(cur, sql, batch, page_size=BATCH)
        total += len(batch)
    conn.commit()
    print(f"  Loaded {total:,} committees ({skipped:,} skipped) in {time.time()-t0:.0f}s")
    return total


def _load_candidates(cur, conn):
    from psycopg2.extras import execute_values
    print("Loading fec_candidates from cn24.zip...")
    t0 = time.time()
    sql = """
        INSERT INTO fec_candidates (
            cand_id, cand_name, cand_pty_affiliation, cand_election_yr,
            cand_office_st, cand_office, cand_office_district, cand_ici,
            cand_status, cand_pcc, cand_st1, cand_st2, cand_city, cand_st, cand_zip
        ) VALUES %s
        ON CONFLICT (cand_id) DO NOTHING
    """
    batch, total, skipped = [], 0, 0
    for r in _stream_rows(FEC_DIR / "cn24.zip"):
        if len(r) < 15 or not r[0]:
            skipped += 1
            continue
        batch.append((
            _truncate(r[0], 9), _truncate(r[1], 200), _truncate(r[2], 3),
            _norm_int(r[3]), _norm_state(r[4]), _truncate(r[5], 1),
            _truncate(r[6], 2), _truncate(r[7], 1), _truncate(r[8], 1),
            _truncate(r[9], 9), _truncate(r[10], 34), _truncate(r[11], 34),
            _truncate(r[12], 30), _norm_state(r[13]), _truncate(r[14], 9),
        ))
        if len(batch) >= 5000:
            execute_values(cur, sql, batch, page_size=5000)
            total += len(batch)
            batch = []
    if batch:
        execute_values(cur, sql, batch, page_size=5000)
        total += len(batch)
    conn.commit()
    print(f"  Loaded {total:,} candidates ({skipped:,} skipped) in {time.time()-t0:.0f}s")
    return total


def _load_indiv(cur, conn):
    from psycopg2.extras import execute_values
    print("Loading fec_individual_contributions from indiv24.zip (this is the big one)...")
    t0 = time.time()
    BATCH = 10000
    sql = """
        INSERT INTO fec_individual_contributions (
            cmte_id, amndt_ind, rpt_tp, transaction_pgi, image_num,
            transaction_tp, entity_tp, name, city, state, zip_code,
            employer, occupation, transaction_dt, transaction_amt,
            other_id, tran_id, file_num, memo_cd, memo_text, sub_id,
            employer_norm
        ) VALUES %s
        ON CONFLICT (sub_id) DO NOTHING
    """
    batch, total, skipped = [], 0, 0
    seen_sub_ids = set()
    for r in _stream_rows(FEC_DIR / "indiv24.zip"):
        if len(r) < 21:
            skipped += 1
            continue
        sub_id = _norm_int(r[20])
        if sub_id is None or sub_id in seen_sub_ids:
            skipped += 1
            continue
        seen_sub_ids.add(sub_id)
        batch.append((
            _truncate(r[0], 9), _truncate(r[1], 1), _truncate(r[2], 3),
            _truncate(r[3], 5), _truncate(r[4], 20), _truncate(r[5], 3),
            _truncate(r[6], 3), _truncate(r[7], 200), _truncate(r[8], 30),
            _norm_state(r[9]), _truncate(r[10], 10), _truncate(r[11], 38),
            _truncate(r[12], 38), _norm_date(r[13]), _norm_decimal(r[14]),
            _truncate(r[15], 9), _truncate(r[16], 40), _norm_int(r[17]),
            _truncate(r[18], 1), _truncate(r[19], 100), sub_id,
            _norm_employer(r[11]),
        ))
        if len(batch) >= BATCH:
            execute_values(cur, sql, batch, page_size=BATCH)
            total += len(batch)
            batch = []
            if total % 200_000 == 0:
                print(f"  Loaded {total:,} rows ({time.time()-t0:.0f}s elapsed)")
    if batch:
        execute_values(cur, sql, batch, page_size=BATCH)
        total += len(batch)
    conn.commit()
    print(f"  Loaded {total:,} individual contributions ({skipped:,} skipped) in {time.time()-t0:.0f}s")
    return total


def _load_pas2(cur, conn):
    from psycopg2.extras import execute_values
    print("Loading fec_committee_contributions from pas224.zip...")
    t0 = time.time()
    BATCH = 10000
    sql = """
        INSERT INTO fec_committee_contributions (
            cmte_id, amndt_ind, rpt_tp, transaction_pgi, image_num,
            transaction_tp, entity_tp, name, city, state, zip_code,
            employer, occupation, transaction_dt, transaction_amt,
            other_id, cand_id, tran_id, file_num, memo_cd, memo_text, sub_id
        ) VALUES %s
        ON CONFLICT (sub_id) DO NOTHING
    """
    batch, total, skipped = [], 0, 0
    seen = set()
    for r in _stream_rows(FEC_DIR / "pas224.zip"):
        if len(r) < 22:
            skipped += 1
            continue
        sub_id = _norm_int(r[21])
        if sub_id is None or sub_id in seen:
            skipped += 1
            continue
        seen.add(sub_id)
        batch.append((
            _truncate(r[0], 9), _truncate(r[1], 1), _truncate(r[2], 3),
            _truncate(r[3], 5), _truncate(r[4], 20), _truncate(r[5], 3),
            _truncate(r[6], 3), _truncate(r[7], 200), _truncate(r[8], 30),
            _norm_state(r[9]), _truncate(r[10], 10), _truncate(r[11], 38),
            _truncate(r[12], 38), _norm_date(r[13]), _norm_decimal(r[14]),
            _truncate(r[15], 9), _truncate(r[16], 9), _truncate(r[17], 40),
            _norm_int(r[18]), _truncate(r[19], 1), _truncate(r[20], 100), sub_id,
        ))
        if len(batch) >= BATCH:
            execute_values(cur, sql, batch, page_size=BATCH)
            total += len(batch)
            batch = []
    if batch:
        execute_values(cur, sql, batch, page_size=BATCH)
        total += len(batch)
    conn.commit()
    print(f"  Loaded {total:,} committee contributions ({skipped:,} skipped) in {time.time()-t0:.0f}s")
    return total


def _update_freshness(cur, conn, indiv_count, pas2_count, cmte_count, cand_count):
    print("Updating data_source_freshness...")
    cur.execute("""
        INSERT INTO data_source_freshness
            (source_name, display_name, last_updated, record_count,
             date_range_start, date_range_end, notes)
        VALUES
            ('fec_individual_contributions', 'FEC Individual Contributions (2023-24 cycle)',
             %s, %s,
             (SELECT MIN(transaction_dt) FROM fec_individual_contributions WHERE transaction_dt IS NOT NULL),
             (SELECT MAX(transaction_dt) FROM fec_individual_contributions WHERE transaction_dt IS NOT NULL),
             '24Q-38 political. FEC bulk indiv24.zip; EMPLOYER field for matching.'),
            ('fec_committees', 'FEC Committees (PACs and Candidate Committees)',
             %s, %s, NULL, NULL,
             '24Q-38 political. FEC committee master cm24.zip; CONNECTED_ORG_NM for corporate PAC matching.'),
            ('fec_candidates', 'FEC Candidates', %s, %s, NULL, NULL,
             '24Q-38 political. FEC candidate master cn24.zip.'),
            ('fec_committee_contributions', 'FEC Committee-to-Candidate Contributions',
             %s, %s, NULL, NULL,
             '24Q-38 political. PAC-to-candidate flows from pas224.zip.')
        ON CONFLICT (source_name) DO UPDATE SET
            last_updated = EXCLUDED.last_updated,
            record_count = EXCLUDED.record_count,
            date_range_start = EXCLUDED.date_range_start,
            date_range_end = EXCLUDED.date_range_end
    """, (
        datetime.now(timezone.utc), indiv_count,
        datetime.now(timezone.utc), cmte_count,
        datetime.now(timezone.utc), cand_count,
        datetime.now(timezone.utc), pas2_count,
    ))
    conn.commit()


def download(name: str, url: str):
    import subprocess
    target = FEC_DIR / name
    target.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {url} -> {target}")
    cmd = [
        "powershell.exe", "-NoProfile", "-Command",
        f"[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; "
        f"Invoke-WebRequest -Uri '{url}' -OutFile '{target}' -UseBasicParsing",
    ]
    subprocess.run(cmd, check=True)
    print(f"  Downloaded {target.stat().st_size / 1e6:.1f} MB")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--redownload", action="store_true",
                        help="Re-fetch all 4 FEC files before loading")
    parser.add_argument("--skip-indiv", action="store_true",
                        help="Skip the (huge) individual contributions file")
    args = parser.parse_args()

    if args.redownload:
        for n, u in URLS.items():
            download(n, u)

    for n in URLS:
        if args.skip_indiv and n == "indiv24.zip":
            continue
        if not (FEC_DIR / n).exists():
            download(n, URLS[n])

    conn = get_connection()
    cur = conn.cursor()

    print("Creating FEC tables (indexes deferred)...")
    conn.autocommit = True
    cur.execute(DDL_TABLES)
    conn.autocommit = False

    cmte_count = _load_committees(cur, conn)
    cand_count = _load_candidates(cur, conn)
    pas2_count = _load_pas2(cur, conn)
    indiv_count = 0 if args.skip_indiv else _load_indiv(cur, conn)

    print("Creating indexes...")
    t0 = time.time()
    conn.autocommit = True
    cur.execute(DDL_INDEXES)
    conn.autocommit = False
    print(f"  Indexes created in {time.time()-t0:.0f}s")

    _update_freshness(cur, conn, indiv_count, pas2_count, cmte_count, cand_count)

    print("\nVerification:")
    print(f"  fec_committees:                {cmte_count:>10,}")
    print(f"  fec_candidates:                {cand_count:>10,}")
    print(f"  fec_committee_contributions:   {pas2_count:>10,}")
    print(f"  fec_individual_contributions:  {indiv_count:>10,}")

    cur.execute("""
        SELECT employer_norm, COUNT(*) AS donations,
               SUM(transaction_amt)::numeric(14,0) AS total
        FROM fec_individual_contributions
        WHERE employer_norm IS NOT NULL
        GROUP BY employer_norm ORDER BY 2 DESC LIMIT 10
    """)
    print("\nTop 10 employers by donor count (this gives a sanity check):")
    for r in cur.fetchall():
        print(f"  {r[0][:45]:<45s} {r[1]:>8,} donations  ${(r[2] or 0):>14,.0f}")

    cur.execute("SELECT COUNT(DISTINCT employer_norm) FROM fec_individual_contributions WHERE employer_norm IS NOT NULL")
    print(f"\n  Distinct normalized employer strings: {cur.fetchone()[0]:,}")

    conn.close()


if __name__ == "__main__":
    main()
