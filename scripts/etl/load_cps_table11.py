"""
Load CPS Table 11 - Employed people by detailed occupation, sex, race, and Hispanic/Latino ethnicity.

Source: cpsaat11.xlsx (project root)
Table: cps_occ_gender_2025

Parses the BLS Current Population Survey Table 11 Excel file and loads
occupation-level demographic breakdowns (gender, race, ethnicity) into
the database. Maps CPS occupation titles to SOC codes using the
oes_occupation_wages table.

Usage:
  py scripts/etl/load_cps_table11.py
  py scripts/etl/load_cps_table11.py --dry-run
  py scripts/etl/load_cps_table11.py --file path/to/cpsaat11.xlsx
"""
from __future__ import annotations

import os
import re
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from db_config import get_connection

try:
    import openpyxl
except ImportError:
    print("ERROR: openpyxl is required. Install with: pip install openpyxl")
    sys.exit(1)


def ts():
    return datetime.now().strftime("%H:%M:%S")


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cps_occ_gender_2025 (
    soc_code VARCHAR(10),
    occupation TEXT,
    total_emp_k NUMERIC,
    pct_women NUMERIC,
    pct_white NUMERIC,
    pct_black NUMERIC,
    pct_asian NUMERIC,
    pct_hispanic NUMERIC,
    year INTEGER DEFAULT 2025,
    PRIMARY KEY (soc_code)
);
"""

UPSERT_SQL = """
INSERT INTO cps_occ_gender_2025
    (soc_code, occupation, total_emp_k, pct_women, pct_white, pct_black, pct_asian, pct_hispanic, year)
VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 2025)
ON CONFLICT (soc_code) DO UPDATE SET
    occupation = EXCLUDED.occupation,
    total_emp_k = EXCLUDED.total_emp_k,
    pct_women = EXCLUDED.pct_women,
    pct_white = EXCLUDED.pct_white,
    pct_black = EXCLUDED.pct_black,
    pct_asian = EXCLUDED.pct_asian,
    pct_hispanic = EXCLUDED.pct_hispanic,
    year = EXCLUDED.year;
"""

# Broad summary titles to skip (top-level and major-group headers)
SKIP_TITLES = {
    "total, 16 years and over",
}


# ---------------------------------------------------------------------------
# Parsing helpers
# ---------------------------------------------------------------------------
def clean_numeric(val):
    """Convert cell value to float, handling en-dashes, dashes, and footnotes."""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip()
    # En-dash (U+2013), em-dash (U+2014), regular dash, asterisks
    if s in ("-", "\u2013", "\u2014", "*", "**", "#", "~", ""):
        return None
    # Strip footnote markers (trailing numbers/letters after space)
    s = re.sub(r'\s*\d+$', '', s)
    s = s.replace(",", "")
    try:
        return float(s)
    except (ValueError, TypeError):
        return None


def normalize_title(title):
    """Normalize an occupation title for matching.

    - Strip leading/trailing whitespace
    - Collapse multiple spaces
    - Remove commas
    - Title case
    - Strip trailing footnote markers
    """
    if not title:
        return ""
    s = str(title).strip()
    # Remove footnote markers (trailing superscript digits)
    s = re.sub(r'\s*\d+$', '', s)
    # Collapse whitespace
    s = re.sub(r'\s+', ' ', s)
    # Remove commas
    s = s.replace(",", "")
    # Title case for consistent matching
    s = s.title()
    return s


def make_fallback_key(title, used_keys=None):
    """Generate a fallback key from occupation title when no SOC match found.

    Produces a key like 'C-ABCDEF' that fits within VARCHAR(10).
    Ensures uniqueness by appending a counter if needed.
    """
    if used_keys is None:
        used_keys = set()
    cleaned = re.sub(r'[^a-zA-Z0-9]', '', title).upper()
    base = f"C-{cleaned[:7]}" if cleaned else "C-UNK"
    # Ensure it fits in 10 chars
    base = base[:10]
    key = base
    counter = 1
    while key in used_keys:
        suffix = str(counter)
        key = base[:10 - len(suffix)] + suffix
        counter += 1
    used_keys.add(key)
    return key


# ---------------------------------------------------------------------------
# SOC Mapping
# ---------------------------------------------------------------------------
def load_oes_titles(conn):
    """Load OES occupation code -> title mapping from database."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT occ_code, occ_title
            FROM oes_occupation_wages
            WHERE o_group = 'detailed'
              AND occ_code IS NOT NULL
              AND occ_title IS NOT NULL
        """)
        rows = cur.fetchall()

    # Build lookup: normalized_title -> occ_code
    title_to_code = {}
    code_to_title = {}
    for occ_code, occ_title in rows:
        norm = normalize_title(occ_title)
        title_to_code[norm] = occ_code
        code_to_title[occ_code] = occ_title
    return title_to_code, code_to_title


def build_abbreviation_map():
    """Common abbreviation patterns for CPS -> OES title matching."""
    return [
        # CPS often combines occupations that OES separates
        ("and fundraising managers", "Managers"),
        # CPS uses "n.e.c." or "all other"
        ("n.e.c.", "All Other"),
        ("not elsewhere classified", "All Other"),
    ]


def map_soc_codes(cps_rows, oes_title_to_code):
    """Map CPS occupation titles to SOC codes using OES titles.

    Two-pass approach:
    1. Exact match on normalized title
    2. Substring/fuzzy match for remaining
    """
    mapped = {}
    unmapped = []
    used_codes = set()

    # Pass 1: Exact match
    for row in cps_rows:
        occ_title = row["occupation"]
        norm = normalize_title(occ_title)

        if norm in oes_title_to_code:
            code = oes_title_to_code[norm]
            if code not in used_codes:
                mapped[occ_title] = code
                used_codes.add(code)
            else:
                # SOC code already used, use fallback
                unmapped.append(row)
        else:
            unmapped.append(row)

    # Pass 2: Substring match for unmatched rows
    still_unmapped = []
    for row in unmapped:
        occ_title = row["occupation"]
        norm = normalize_title(occ_title)
        found = False

        # Try substring: CPS title contained in OES title or vice versa
        best_match = None
        best_len = 0
        for oes_norm, oes_code in oes_title_to_code.items():
            if oes_code in used_codes:
                continue
            # Check if one contains the other
            if norm in oes_norm or oes_norm in norm:
                # Prefer longer matches (more specific)
                match_len = min(len(norm), len(oes_norm))
                if match_len > best_len:
                    best_len = match_len
                    best_match = oes_code

        # Also try without "and" variations
        if not best_match:
            # Try splitting on " And " and matching parts
            parts = norm.split(" And ")
            if len(parts) >= 2:
                for oes_norm, oes_code in oes_title_to_code.items():
                    if oes_code in used_codes:
                        continue
                    # Check if first part matches start of OES title
                    if oes_norm.startswith(parts[0].strip()):
                        best_match = oes_code
                        break

        if best_match:
            mapped[occ_title] = best_match
            used_codes.add(best_match)
        else:
            still_unmapped.append(row)

    return mapped, still_unmapped


# ---------------------------------------------------------------------------
# Excel parsing
# ---------------------------------------------------------------------------
def parse_excel(xlsx_path):
    """Parse CPS Table 11 Excel file into list of row dicts."""
    print(f"[{ts()}] Loading workbook: {xlsx_path}")
    wb = openpyxl.load_workbook(xlsx_path, data_only=True)
    ws = wb.active

    rows = []
    skipped_empty = 0
    skipped_header = 0
    skipped_summary = 0

    # Data starts at row 8 (after header rows 1-7)
    # Columns: A=Occupation, B=Total employed, C=% Women, D=% White,
    #          E=% Black, F=% Asian, G=% Hispanic
    for row_num, row in enumerate(ws.iter_rows(min_row=8, values_only=False), start=8):
        occ_cell = row[0]
        occ_val = occ_cell.value

        # Skip empty rows
        if occ_val is None or str(occ_val).strip() == "":
            skipped_empty += 1
            continue

        occ_title = str(occ_val).strip()

        # Skip the NOTE row at the bottom
        if occ_title.upper().startswith("NOTE:"):
            continue

        # Skip broad summary rows (indent 0 = top-level summaries)
        indent = 0
        if occ_cell.alignment:
            indent = int(occ_cell.alignment.indent) if occ_cell.alignment.indent else 0

        # Skip indent 0 (top-level: "Total, 16 years and over", major occupation groups)
        # and indent 1 (sub-group headers like "Management, business, and financial operations")
        if indent <= 1:
            skipped_summary += 1
            continue

        # Also skip known summary titles even if indented
        if occ_title.lower() in SKIP_TITLES:
            skipped_summary += 1
            continue

        total_emp = clean_numeric(row[1].value)
        pct_women = clean_numeric(row[2].value)
        pct_white = clean_numeric(row[3].value)
        pct_black = clean_numeric(row[4].value)
        pct_asian = clean_numeric(row[5].value)
        pct_hispanic = clean_numeric(row[6].value)

        # Skip rows with no total employment (shouldn't happen after indent filter, but safety)
        if total_emp is None:
            skipped_header += 1
            continue

        rows.append({
            "occupation": occ_title,
            "total_emp_k": total_emp,
            "pct_women": pct_women,
            "pct_white": pct_white,
            "pct_black": pct_black,
            "pct_asian": pct_asian,
            "pct_hispanic": pct_hispanic,
            "indent": indent,
        })

    wb.close()
    print(f"[{ts()}] Parsed {len(rows)} data rows "
          f"(skipped: {skipped_empty} empty, {skipped_summary} summary, {skipped_header} no-data)")
    return rows


# ---------------------------------------------------------------------------
# Database loading
# ---------------------------------------------------------------------------
def create_table(conn):
    """Create the cps_occ_gender_2025 table."""
    with conn.cursor() as cur:
        cur.execute("DROP TABLE IF EXISTS cps_occ_gender_2025 CASCADE")
        cur.execute(CREATE_TABLE_SQL)
    conn.commit()
    print(f"[{ts()}] Table cps_occ_gender_2025 created")


def load_data(conn, cps_rows, soc_map, dry_run=False):
    """Insert parsed CPS data into the database."""
    if dry_run:
        print(f"[{ts()}] DRY RUN - would load {len(cps_rows)} rows")
        return 0

    loaded = 0
    used_keys = set(soc_map.values())  # Track used SOC codes for fallback uniqueness
    with conn.cursor() as cur:
        for row in cps_rows:
            occ = row["occupation"]
            soc_code = soc_map.get(occ)
            if soc_code is None:
                soc_code = make_fallback_key(occ, used_keys)

            cur.execute(UPSERT_SQL, (
                soc_code,
                occ,
                row["total_emp_k"],
                row["pct_women"],
                row["pct_white"],
                row["pct_black"],
                row["pct_asian"],
                row["pct_hispanic"],
            ))
            loaded += 1
    conn.commit()
    return loaded


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def parse_args():
    ap = argparse.ArgumentParser(description="Load CPS Table 11 occupation demographics")
    ap.add_argument("--file", default=None,
                    help="Path to cpsaat11.xlsx (default: project root)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Parse file but do not write to database")
    return ap.parse_args()


def main():
    args = parse_args()

    # Resolve Excel file path
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    xlsx_path = args.file or os.path.join(project_root, "cpsaat11.xlsx")

    if not os.path.exists(xlsx_path):
        print(f"ERROR: File not found: {xlsx_path}")
        sys.exit(1)

    # Parse Excel
    cps_rows = parse_excel(xlsx_path)
    if not cps_rows:
        print("ERROR: No data rows parsed from Excel file")
        sys.exit(1)

    # Connect and load OES titles for SOC mapping
    conn = get_connection()
    try:
        print(f"[{ts()}] Loading OES occupation titles for SOC mapping...")
        oes_title_to_code, _ = load_oes_titles(conn)
        print(f"[{ts()}] Loaded {len(oes_title_to_code)} OES occupation titles")

        # Map CPS titles to SOC codes
        soc_map, unmapped_rows = map_soc_codes(cps_rows, oes_title_to_code)
        mapped_count = len(soc_map)
        unmapped_count = len(unmapped_rows)
        total_count = len(cps_rows)

        print(f"[{ts()}] SOC mapping results:")
        print(f"  Total CPS occupations: {total_count}")
        print(f"  Mapped to SOC code:    {mapped_count}")
        print(f"  Unmapped (fallback):   {unmapped_count}")

        if unmapped_rows and unmapped_count <= 30:
            preview_keys = set(soc_map.values())
            print(f"[{ts()}] Unmapped occupations:")
            for row in unmapped_rows:
                fb = make_fallback_key(row["occupation"], preview_keys)
                print(f"  {fb} <- {row['occupation']}")

        # Create table and load
        if not args.dry_run:
            create_table(conn)
            loaded = load_data(conn, cps_rows, soc_map, dry_run=args.dry_run)
            print(f"[{ts()}] Loaded {loaded} rows into cps_occ_gender_2025")

            # Verify
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) FROM cps_occ_gender_2025")
                db_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM cps_occ_gender_2025 WHERE soc_code LIKE 'C-%%'")
                fallback_count = cur.fetchone()[0]
                cur.execute("SELECT COUNT(*) FROM cps_occ_gender_2025 WHERE soc_code NOT LIKE 'C-%%'")
                soc_count = cur.fetchone()[0]

            print(f"\n[{ts()}] === Summary ===")
            print(f"  Rows in table:         {db_count}")
            print(f"  With SOC code:         {soc_count}")
            print(f"  With fallback key:     {fallback_count}")
            print(f"  Match rate:            {soc_count/db_count*100:.1f}%" if db_count else "  Match rate: N/A")
        else:
            print(f"[{ts()}] DRY RUN complete - no database changes made")

    finally:
        conn.close()

    print(f"[{ts()}] Done.")


if __name__ == "__main__":
    main()
