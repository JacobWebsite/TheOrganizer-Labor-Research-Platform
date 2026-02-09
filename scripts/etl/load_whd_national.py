import os
"""
Load national WHD WHISARD dataset into PostgreSQL.

Source: whd_whisard_20260116.csv (363K cases, 110 columns)
Target: whd_cases table in olms_multiyear

Usage:
    py scripts/etl/load_whd_national.py
"""

import re
import sys
import time
import math
import pandas as pd
import psycopg2
from psycopg2.extras import execute_values

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
CSV_PATH = r"C:\Users\jakew\Downloads\labor-data-project\whd_whisard_20260116.csv\whd_whisard.csv"
BATCH_SIZE = 5000

DB_PARAMS = dict(
    host="localhost",
    dbname="olms_multiyear",
    user="postgres",
    password="os.environ.get('DB_PASSWORD', '')",
)

# ---------------------------------------------------------------------------
# Column mapping: csv_col -> db_col
# ---------------------------------------------------------------------------
COLUMN_MAP = {
    "case_id":              "case_id",
    "trade_nm":             "trade_name",
    "legal_name":           "legal_name",
    "street_addr_1_txt":    "street_address",
    "cty_nm":               "city",
    "st_cd":                "state",
    "zip_cd":               "zip_code",
    "naic_cd":              "naics_code",
    "case_violtn_cnt":      "total_violations",
    "cmp_assd":             "civil_penalties",
    "ee_violtd_cnt":        "employees_violated",
    "bw_atp_amt":           "backwages_amount",
    "ee_atp_cnt":           "employees_backwages",
    "flsa_violtn_cnt":      "flsa_violations",
    "flsa_bw_atp_amt":      "flsa_backwages",
    "flsa_ot_bw_atp_amt":   "flsa_overtime_backwages",
    "flsa_mw_bw_atp_amt":   "flsa_mw_backwages",
    "flsa_cl_violtn_cnt":   "flsa_child_labor_violations",
    "flsa_cl_minor_cnt":    "flsa_child_labor_minors",
    "flsa_repeat_violator": "flsa_repeat_violator",
    "findings_start_date":  "findings_start_date",
    "findings_end_date":    "findings_end_date",
}

# Integer columns (violation counts, employee counts)
INT_COLS = [
    "total_violations",
    "employees_violated",
    "employees_backwages",
    "flsa_violations",
    "flsa_child_labor_violations",
    "flsa_child_labor_minors",
]

# Numeric / money columns
NUMERIC_COLS = [
    "civil_penalties",
    "backwages_amount",
    "flsa_backwages",
    "flsa_overtime_backwages",
    "flsa_mw_backwages",
]

# Date columns
DATE_COLS = [
    "findings_start_date",
    "findings_end_date",
]

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
CREATE_TABLE = """
DROP TABLE IF EXISTS whd_cases CASCADE;

CREATE TABLE whd_cases (
    id                          SERIAL PRIMARY KEY,
    case_id                     VARCHAR(20),
    trade_name                  TEXT,
    legal_name                  TEXT,
    name_normalized             TEXT,
    street_address              TEXT,
    city                        TEXT,
    state                       VARCHAR(2),
    zip_code                    VARCHAR(10),
    naics_code                  VARCHAR(10),
    total_violations            INTEGER,
    civil_penalties             NUMERIC,
    employees_violated          INTEGER,
    backwages_amount            NUMERIC,
    employees_backwages         INTEGER,
    flsa_violations             INTEGER,
    flsa_backwages              NUMERIC,
    flsa_overtime_backwages     NUMERIC,
    flsa_mw_backwages           NUMERIC,
    flsa_child_labor_violations INTEGER,
    flsa_child_labor_minors     INTEGER,
    flsa_repeat_violator        BOOLEAN,
    findings_start_date         DATE,
    findings_end_date           DATE,
    created_at                  TIMESTAMP DEFAULT NOW()
);
"""

INDEX_SQL = [
    "CREATE INDEX idx_whd_state ON whd_cases(state);",
    "CREATE INDEX idx_whd_name_state ON whd_cases(name_normalized, state);",
    "CREATE INDEX idx_whd_name_city ON whd_cases(name_normalized, city);",
    "CREATE INDEX idx_whd_case_id ON whd_cases(case_id);",
    "CREATE INDEX idx_whd_naics ON whd_cases(naics_code);",
]

# Ordered DB columns for INSERT (excluding id and created_at)
INSERT_COLS = [
    "case_id", "trade_name", "legal_name", "name_normalized",
    "street_address", "city", "state", "zip_code", "naics_code",
    "total_violations", "civil_penalties", "employees_violated",
    "backwages_amount", "employees_backwages",
    "flsa_violations", "flsa_backwages", "flsa_overtime_backwages",
    "flsa_mw_backwages", "flsa_child_labor_violations",
    "flsa_child_labor_minors", "flsa_repeat_violator",
    "findings_start_date", "findings_end_date",
]

INSERT_SQL = (
    "INSERT INTO whd_cases ("
    + ", ".join(INSERT_COLS)
    + ") VALUES %s"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
LEGAL_SUFFIX_RE = re.compile(
    r"\b(inc|llc|llp|ltd|corp|co|company|incorporated|corporation|limited|lp|pllc|pc|pa|dba)\b"
)


def normalize_name(trade_name, legal_name):
    """Generate a normalized employer name for matching."""
    raw = (trade_name if pd.notna(trade_name) and str(trade_name).strip() else
           legal_name if pd.notna(legal_name) and str(legal_name).strip() else "")
    name = str(raw).strip().lower()
    name = LEGAL_SUFFIX_RE.sub("", name)
    name = re.sub(r"[^a-z0-9 ]", "", name)
    name = re.sub(r"\s+", " ", name).strip()
    return name if name else None


def safe_int(val):
    """Convert value to int, returning None for NaN/empty."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def safe_float(val):
    """Convert value to float/Decimal-compatible, returning None for NaN."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def safe_str(val):
    """Convert value to stripped string, returning None for NaN/empty."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    s = str(val).strip()
    return s if s else None


def safe_date(val):
    """Convert date string to date or None."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    s = str(val).strip()
    if not s:
        return None
    try:
        return pd.Timestamp(s).date()
    except Exception:
        return None


def convert_repeat_violator(val):
    """
    Convert flsa_repeat_violator to boolean.
    Actual values in data: 'R' (repeat), 'W' (willful), 'RW' (both), NaN (none).
    Any non-empty value means True (flagged as repeat/willful violator).
    """
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    s = str(val).strip().upper()
    if not s:
        return None
    # R, W, RW all indicate repeat/willful violation status
    if s in ("R", "W", "RW", "Y", "YES", "TRUE", "1"):
        return True
    if s in ("N", "NO", "FALSE", "0"):
        return False
    # Any other non-empty value -> True (flagged)
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    t0 = time.time()

    # --- Read CSV ---
    print("Reading CSV ...")
    try:
        df = pd.read_csv(
            CSV_PATH,
            dtype={"naic_cd": str, "zip_cd": str, "case_id": str},
            low_memory=False,
            encoding="latin-1",
        )
    except UnicodeDecodeError:
        print("  latin-1 failed, trying utf-8 with errors='replace' ...")
        df = pd.read_csv(
            CSV_PATH,
            dtype={"naic_cd": str, "zip_cd": str, "case_id": str},
            low_memory=False,
            encoding="utf-8",
            errors="replace",
        )

    print("  Rows read: %d" % len(df))
    print("  Columns: %d" % len(df.columns))

    # --- Rename columns ---
    csv_cols_present = [c for c in COLUMN_MAP if c in df.columns]
    missing = [c for c in COLUMN_MAP if c not in df.columns]
    if missing:
        print("  WARNING: missing CSV columns: %s" % missing)

    df_mapped = df[csv_cols_present].rename(columns=COLUMN_MAP)

    # --- Compute name_normalized (vectorized) ---
    print("Computing name_normalized ...")
    # Pick trade_name first, fall back to legal_name
    raw_name = df_mapped["trade_name"].fillna(df_mapped["legal_name"]).fillna("")
    norm = raw_name.str.strip().str.lower()
    norm = norm.str.replace(
        r"\b(inc|llc|llp|ltd|corp|co|company|incorporated|corporation|limited|lp|pllc|pc|pa|dba)\b",
        "", regex=True
    )
    norm = norm.str.replace(r"[^a-z0-9 ]", "", regex=True)
    norm = norm.str.replace(r"\s+", " ", regex=True).str.strip()
    norm = norm.replace("", pd.NA)
    df_mapped["name_normalized"] = norm

    # --- Pre-process columns for fast tuple building ---
    print("Converting columns ...")

    # Integer columns: coerce to nullable int
    int_set = set(INT_COLS)
    for col in INT_COLS:
        if col in df_mapped.columns:
            df_mapped[col] = pd.to_numeric(df_mapped[col], errors="coerce")

    # Numeric columns: coerce to float
    for col in NUMERIC_COLS:
        if col in df_mapped.columns:
            df_mapped[col] = pd.to_numeric(df_mapped[col], errors="coerce")

    # Date columns: parse to datetime
    for col in DATE_COLS:
        if col in df_mapped.columns:
            df_mapped[col] = pd.to_datetime(df_mapped[col], errors="coerce")

    # State: truncate to 2 chars
    if "state" in df_mapped.columns:
        df_mapped["state"] = df_mapped["state"].astype(str).str.strip().str[:2]
        df_mapped.loc[df_mapped["state"].isin(["", "nan", "None"]), "state"] = None

    # Zip code: pad to 5 digits
    if "zip_code" in df_mapped.columns:
        zc = df_mapped["zip_code"].astype(str).str.strip()
        zc = zc.where(~zc.isin(["", "nan", "None"]), other=None)
        # Pad numeric zips shorter than 5 digits
        mask_short = zc.notna() & zc.str.match(r"^\d{1,4}$")
        zc.loc[mask_short] = zc.loc[mask_short].str.zfill(5)
        df_mapped["zip_code"] = zc.str[:10]

    # NAICS: strip leading zeros
    if "naics_code" in df_mapped.columns:
        nc = df_mapped["naics_code"].astype(str).str.strip()
        nc = nc.where(~nc.isin(["", "nan", "None"]), other=None)
        nc = nc.where(nc.isna(), nc.str.lstrip("0"))
        nc = nc.where(nc.isna() | (nc != ""), "0")
        df_mapped["naics_code"] = nc.str[:10]

    # Repeat violator: convert to boolean
    if "flsa_repeat_violator" in df_mapped.columns:
        rv = df_mapped["flsa_repeat_violator"].astype(str).str.strip().str.upper()
        rv_bool = pd.Series([None] * len(rv), dtype=object)
        rv_bool[rv.isin(["R", "W", "RW", "Y", "YES", "TRUE", "1"])] = True
        rv_bool[rv.isin(["N", "NO", "FALSE", "0"])] = False
        # NaN/empty stays None
        df_mapped["flsa_repeat_violator"] = rv_bool

    # --- Build row tuples using itertuples (much faster than iterrows) ---
    print("Building row tuples ...")

    # Replace NaN/NaT with None across the board for DB compatibility
    df_insert = df_mapped[INSERT_COLS].copy()
    df_insert = df_insert.where(df_insert.notna(), other=None)

    rows = []
    for tup in df_insert.itertuples(index=False, name=None):
        converted = []
        for i, col in enumerate(INSERT_COLS):
            val = tup[i]
            if val is None or val is pd.NaT:
                converted.append(None)
            elif col in int_set:
                try:
                    converted.append(int(float(val)))
                except (ValueError, TypeError):
                    converted.append(None)
            elif col in DATE_COLS:
                try:
                    converted.append(val.date() if hasattr(val, "date") else val)
                except Exception:
                    converted.append(None)
            else:
                converted.append(val)
        rows.append(tuple(converted))

    print("  Tuples prepared: %d" % len(rows))

    # --- Database load ---
    print("Connecting to database ...")
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # Create table
        print("Creating table whd_cases ...")
        cur.execute(CREATE_TABLE)
        conn.commit()

        # Bulk insert in batches
        total_batches = (len(rows) + BATCH_SIZE - 1) // BATCH_SIZE
        print("Inserting %d rows in %d batches ..." % (len(rows), total_batches))

        for i in range(0, len(rows), BATCH_SIZE):
            batch = rows[i : i + BATCH_SIZE]
            execute_values(cur, INSERT_SQL, batch, page_size=BATCH_SIZE)
            conn.commit()
            batch_num = (i // BATCH_SIZE) + 1
            if batch_num % 10 == 0 or batch_num == total_batches:
                print("  Batch %d/%d (%d rows)" % (batch_num, total_batches, i + len(batch)))

        # Create indexes
        print("Creating indexes ...")
        for idx_sql in INDEX_SQL:
            cur.execute(idx_sql)
            conn.commit()

        # --- Summary ---
        print("")
        print("=" * 60)
        print("LOAD COMPLETE")
        print("=" * 60)

        cur.execute("SELECT COUNT(*) FROM whd_cases;")
        total = cur.fetchone()[0]
        print("Total rows loaded: %d" % total)

        cur.execute("""
            SELECT state, COUNT(*) AS cnt
            FROM whd_cases
            WHERE state IS NOT NULL
            GROUP BY state
            ORDER BY cnt DESC
            LIMIT 10;
        """)
        print("")
        print("Top 10 states:")
        for row in cur.fetchall():
            print("  %s: %s" % (row[0], "{:,}".format(row[1])))

        cur.execute("SELECT COALESCE(SUM(backwages_amount), 0) FROM whd_cases;")
        bw = cur.fetchone()[0]
        print("")
        print("Total backwages: $%s" % "{:,.2f}".format(float(bw)))

        cur.execute("SELECT COALESCE(SUM(civil_penalties), 0) FROM whd_cases;")
        pen = cur.fetchone()[0]
        print("Total civil penalties: $%s" % "{:,.2f}".format(float(pen)))

        cur.execute("""
            SELECT MIN(findings_start_date), MAX(findings_end_date)
            FROM whd_cases
            WHERE findings_start_date IS NOT NULL;
        """)
        dates = cur.fetchone()
        print("")
        print("Date range: %s to %s" % (dates[0], dates[1]))

        cur.execute("SELECT COUNT(*) FROM whd_cases WHERE total_violations > 0;")
        with_viol = cur.fetchone()[0]
        print("Rows with violations > 0: %s (%s%%)" % (
            "{:,}".format(with_viol),
            round(100.0 * with_viol / total, 1) if total else 0,
        ))

        cur.execute("SELECT COUNT(*) FROM whd_cases WHERE flsa_repeat_violator = TRUE;")
        repeat = cur.fetchone()[0]
        print("FLSA repeat/willful violators: %s" % "{:,}".format(repeat))

        cur.execute("SELECT COUNT(*) FROM whd_cases WHERE name_normalized IS NOT NULL;")
        named = cur.fetchone()[0]
        print("Rows with name_normalized: %s (%s%%)" % (
            "{:,}".format(named),
            round(100.0 * named / total, 1) if total else 0,
        ))

        elapsed = time.time() - t0
        print("")
        print("Elapsed: %.1f seconds" % elapsed)

    except Exception as e:
        conn.rollback()
        print("ERROR: %s" % str(e))
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
