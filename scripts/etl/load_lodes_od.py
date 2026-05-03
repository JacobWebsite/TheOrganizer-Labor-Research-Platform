"""
Load LODES OD (origin-destination) and WAC (workplace area characteristics)
with typed columns into `lodes_od_<year>` and `lodes_wac_<year>`.

Unlike `newsrc_load_lodes.py` (which loads all files, all-TEXT, all states), this
loader:
  - Filters to the requested states (default: ny).
  - Uses typed INTEGER columns + a primary key + tract-level indexes, so
    aggregations like "SUM(s000) WHERE w_tract = X" are cheap.
  - Derives `w_state` from the first two chars of `w_geocode` and stamps
    `od_type` ('main' or 'aux') per file.
  - Is idempotent: skips a file that already loaded unless --truncate is set.

Usage:
  py scripts/etl/load_lodes_od.py --states ny --year 2022
  py scripts/etl/load_lodes_od.py --states ny,nj --year 2022 --truncate
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection  # noqa: E402

from newsrc_common import DEFAULT_SOURCE_ROOT, open_gzip_text  # noqa: E402


STATE_FIPS = {
    "ak": "02", "al": "01", "ar": "05", "az": "04", "ca": "06", "co": "08",
    "ct": "09", "dc": "11", "de": "10", "fl": "12", "ga": "13", "hi": "15",
    "ia": "19", "id": "16", "il": "17", "in": "18", "ks": "20", "ky": "21",
    "la": "22", "ma": "25", "md": "24", "me": "23", "mi": "26", "mn": "27",
    "mo": "29", "ms": "28", "mt": "30", "nc": "37", "nd": "38", "ne": "31",
    "nh": "33", "nj": "34", "nm": "35", "nv": "32", "ny": "36", "oh": "39",
    "ok": "40", "or": "41", "pa": "42", "ri": "44", "sc": "45", "sd": "46",
    "tn": "47", "tx": "48", "ut": "49", "va": "51", "vt": "50", "wa": "53",
    "wi": "55", "wv": "54", "wy": "56",
}


OD_COLS = [
    "w_geocode", "h_geocode", "s000",
    "sa01", "sa02", "sa03",
    "se01", "se02", "se03",
    "si01", "si02", "si03",
    "createdate",
]

WAC_COLS = [
    "w_geocode", "c000",
    "ca01", "ca02", "ca03",
    "ce01", "ce02", "ce03",
    "cns01", "cns02", "cns03", "cns04", "cns05",
    "cns06", "cns07", "cns08", "cns09", "cns10",
    "cns11", "cns12", "cns13", "cns14", "cns15",
    "cns16", "cns17", "cns18", "cns19", "cns20",
    "cr01", "cr02", "cr03", "cr04", "cr05", "cr07",
    "ct01", "ct02",
    "cd01", "cd02", "cd03", "cd04",
    "cs01", "cs02",
    "cfa01", "cfa02", "cfa03", "cfa04", "cfa05",
    "cfs01", "cfs02", "cfs03", "cfs04", "cfs05",
    "createdate",
]


def parse_args():
    ap = argparse.ArgumentParser(description="Load LODES OD+WAC typed tables")
    ap.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    ap.add_argument("--subdir", default="LODES_bulk_2022")
    ap.add_argument("--states", default="ny", help="Comma list of 2-letter state codes")
    ap.add_argument("--year", type=int, default=2022)
    ap.add_argument("--truncate", action="store_true")
    ap.add_argument("--skip-od", action="store_true")
    ap.add_argument("--skip-wac", action="store_true")
    return ap.parse_args()


def create_target_tables(conn, year: int, truncate: bool):
    od_table = f"lodes_od_{year}"
    wac_table = f"lodes_wac_{year}"

    int_cols_od = [c for c in OD_COLS if c not in ("w_geocode", "h_geocode", "createdate")]
    int_cols_wac = [c for c in WAC_COLS if c not in ("w_geocode", "createdate")]

    ddl_od = f"""
    CREATE TABLE IF NOT EXISTS {od_table} (
        w_state     CHAR(2) NOT NULL,
        w_geocode   CHAR(15) NOT NULL,
        h_geocode   CHAR(15) NOT NULL,
        od_type     CHAR(4) NOT NULL,
        {", ".join(f"{c} INTEGER" for c in int_cols_od)},
        createdate  DATE,
        _source_file TEXT,
        _loaded_at   TIMESTAMP DEFAULT NOW(),
        PRIMARY KEY (w_geocode, h_geocode, od_type)
    );
    """
    ddl_wac = f"""
    CREATE TABLE IF NOT EXISTS {wac_table} (
        w_state     CHAR(2) NOT NULL,
        w_geocode   CHAR(15) NOT NULL PRIMARY KEY,
        {", ".join(f"{c} INTEGER" for c in int_cols_wac)},
        createdate  DATE,
        _source_file TEXT,
        _loaded_at   TIMESTAMP DEFAULT NOW()
    );
    """
    with conn.cursor() as cur:
        cur.execute(ddl_od)
        cur.execute(ddl_wac)
        if truncate:
            cur.execute(f"TRUNCATE TABLE {od_table}")
            cur.execute(f"TRUNCATE TABLE {wac_table}")
    conn.commit()
    return od_table, wac_table


def create_indexes(conn, od_table: str, wac_table: str):
    stmts = [
        f"CREATE INDEX IF NOT EXISTS idx_{od_table}_wtract ON {od_table} (SUBSTRING(w_geocode, 1, 11))",
        f"CREATE INDEX IF NOT EXISTS idx_{od_table}_htract ON {od_table} (SUBSTRING(h_geocode, 1, 11))",
        f"CREATE INDEX IF NOT EXISTS idx_{od_table}_wstate ON {od_table} (w_state)",
        f"CREATE INDEX IF NOT EXISTS idx_{wac_table}_wtract ON {wac_table} (SUBSTRING(w_geocode, 1, 11))",
        f"CREATE INDEX IF NOT EXISTS idx_{wac_table}_wstate ON {wac_table} (w_state)",
    ]
    with conn.cursor() as cur:
        for s in stmts:
            cur.execute(s)
    conn.commit()


def already_loaded(conn, table: str, source_file: str) -> bool:
    with conn.cursor() as cur:
        cur.execute(f"SELECT 1 FROM {table} WHERE _source_file = %s LIMIT 1", [source_file])
        return cur.fetchone() is not None


def load_od_file(conn, table: str, path: Path, od_type: str, state_fips: str) -> int:
    """COPY one ny_od_{main|aux} file into lodes_od_<year>."""
    staging = "_stg_lodes_od"
    col_sql = ", ".join(OD_COLS)
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {staging}")
        cur.execute(f"""
            CREATE TEMP TABLE {staging} (
                w_geocode TEXT, h_geocode TEXT,
                s000 INTEGER,
                sa01 INTEGER, sa02 INTEGER, sa03 INTEGER,
                se01 INTEGER, se02 INTEGER, se03 INTEGER,
                si01 INTEGER, si02 INTEGER, si03 INTEGER,
                createdate TEXT
            ) ON COMMIT DROP
        """)
        with open_gzip_text(path) as stream:
            cur.copy_expert(
                f"COPY {staging} ({col_sql}) FROM STDIN WITH (FORMAT csv, HEADER true)",
                stream,
            )
        cur.execute(f"""
            INSERT INTO {table}
                (w_state, w_geocode, h_geocode, od_type,
                 s000, sa01, sa02, sa03, se01, se02, se03, si01, si02, si03,
                 createdate, _source_file)
            SELECT %s, w_geocode, h_geocode, %s,
                   s000, sa01, sa02, sa03, se01, se02, se03, si01, si02, si03,
                   TO_DATE(createdate, 'YYYYMMDD'), %s
              FROM {staging}
            ON CONFLICT (w_geocode, h_geocode, od_type) DO NOTHING
        """, [state_fips, od_type, path.name])
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE _source_file = %s", [path.name])
        inserted = cur.fetchone()[0]
    conn.commit()
    return inserted


def load_wac_file(conn, table: str, path: Path, state_fips: str) -> int:
    staging = "_stg_lodes_wac"
    col_sql = ", ".join(WAC_COLS)
    int_sql = ", ".join(c for c in WAC_COLS if c not in ("w_geocode", "createdate"))
    with conn.cursor() as cur:
        cur.execute(f"DROP TABLE IF EXISTS {staging}")
        int_defs = ", ".join(f"{c} INTEGER" for c in WAC_COLS if c not in ("w_geocode", "createdate"))
        cur.execute(f"""
            CREATE TEMP TABLE {staging} (
                w_geocode TEXT,
                {int_defs},
                createdate TEXT
            ) ON COMMIT DROP
        """)
        with open_gzip_text(path) as stream:
            cur.copy_expert(
                f"COPY {staging} ({col_sql}) FROM STDIN WITH (FORMAT csv, HEADER true)",
                stream,
            )
        cur.execute(f"""
            INSERT INTO {table}
                (w_state, w_geocode, {int_sql}, createdate, _source_file)
            SELECT %s, w_geocode, {int_sql},
                   TO_DATE(createdate, 'YYYYMMDD'), %s
              FROM {staging}
            ON CONFLICT (w_geocode) DO NOTHING
        """, [state_fips, path.name])
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE _source_file = %s", [path.name])
        inserted = cur.fetchone()[0]
    conn.commit()
    return inserted


def main():
    args = parse_args()
    src = Path(args.source_root) / args.subdir
    if not src.exists():
        raise SystemExit(f"Source dir missing: {src}")

    states = [s.strip().lower() for s in args.states.split(",") if s.strip()]
    bad = [s for s in states if s not in STATE_FIPS]
    if bad:
        raise SystemExit(f"Unknown state codes: {bad}")

    conn = get_connection()
    try:
        od_table, wac_table = create_target_tables(conn, args.year, args.truncate)

        for st in states:
            fips = STATE_FIPS[st]
            print(f"\n=== {st.upper()} (FIPS {fips}) ===")

            if not args.skip_od:
                for od_type in ("main", "aux"):
                    fname = f"{st}_od_{od_type}_JT00_{args.year}.csv.gz"
                    path = src / fname
                    if not path.exists():
                        print(f"  [skip] {fname} (not on disk)")
                        continue
                    if not args.truncate and already_loaded(conn, od_table, fname):
                        print(f"  [skip] {fname} (already loaded)")
                        continue
                    t0 = time.time()
                    n = load_od_file(conn, od_table, path, od_type, fips)
                    print(f"  [ok]   {fname} -> {od_table}  rows={n:,}  {time.time()-t0:.1f}s")

            if not args.skip_wac:
                fname = f"{st}_wac_S000_JT00_{args.year}.csv.gz"
                path = src / fname
                if not path.exists():
                    print(f"  [skip] {fname} (not on disk)")
                    continue
                if not args.truncate and already_loaded(conn, wac_table, fname):
                    print(f"  [skip] {fname} (already loaded)")
                    continue
                t0 = time.time()
                n = load_wac_file(conn, wac_table, path, fips)
                print(f"  [ok]   {fname} -> {wac_table}  rows={n:,}  {time.time()-t0:.1f}s")

        print("\nCreating indexes...")
        create_indexes(conn, od_table, wac_table)

        with conn.cursor() as cur:
            cur.execute(f"SELECT COUNT(*), SUM(s000) FROM {od_table}")
            od_rows, od_jobs = cur.fetchone()
            cur.execute(f"SELECT COUNT(*), SUM(c000) FROM {wac_table}")
            wac_rows, wac_jobs = cur.fetchone()
        print(f"\n{od_table}: {od_rows:,} rows, {od_jobs or 0:,} total jobs")
        print(f"{wac_table}: {wac_rows:,} rows, {wac_jobs or 0:,} total jobs")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
