"""Script 11: Extract structured values (dollars, percentages, day counts) from provisions.

Stores extracted values in cba_provisions.extracted_values JSONB column.

Usage:
    py scripts/cba/11_extract_values.py                   # All contracts
    py scripts/cba/11_extract_values.py --cba-id 26       # Single contract
    py scripts/cba/11_extract_values.py --verbose          # Detailed output
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

# Extraction patterns
DOLLAR_RE = re.compile(
    r'\$\s*([\d,]+(?:\.\d{1,2})?)\s*'
    r'(?:per\s+(hour|month|week|year|day|employee|capita|annum|pay\s+period|visit))?',
    re.IGNORECASE,
)

PERCENTAGE_RE = re.compile(
    r'(\d+(?:\.\d+)?)\s*(%|percent)',
    re.IGNORECASE,
)

DAY_COUNT_RE = re.compile(
    r'(\d+)\s+(calendar\s+|working\s+|business\s+)?days?',
    re.IGNORECASE,
)

TIME_PERIOD_RE = re.compile(
    r'(\d+)\s+(months?|years?|weeks?|hours?)',
    re.IGNORECASE,
)


def extract_values(text: str) -> dict:
    """Extract structured values from provision text."""
    result = {}

    # Dollar amounts
    dollars = []
    for m in DOLLAR_RE.finditer(text):
        raw_val = m.group(1).replace(',', '')
        try:
            value = float(raw_val)
        except ValueError:
            continue
        unit = m.group(2).lower().strip() if m.group(2) else None
        entry = {"value": value, "raw": m.group(0).strip()}
        if unit:
            entry["unit"] = "per " + unit
        dollars.append(entry)
    if dollars:
        result["dollar_amounts"] = dollars

    # Percentages
    pcts = []
    for m in PERCENTAGE_RE.finditer(text):
        try:
            value = float(m.group(1))
        except ValueError:
            continue
        pcts.append({"value": value, "raw": m.group(0).strip()})
    if pcts:
        result["percentages"] = pcts

    # Day counts
    days = []
    for m in DAY_COUNT_RE.finditer(text):
        try:
            value = int(m.group(1))
        except ValueError:
            continue
        qualifier = m.group(2).strip().rstrip() if m.group(2) else None
        entry = {"value": value, "raw": m.group(0).strip()}
        if qualifier:
            entry["qualifier"] = qualifier.strip()
        days.append(entry)
    if days:
        result["day_counts"] = days

    # Time periods
    periods = []
    for m in TIME_PERIOD_RE.finditer(text):
        try:
            value = int(m.group(1))
        except ValueError:
            continue
        unit = m.group(2).lower().strip()
        periods.append({"value": value, "unit": unit, "raw": m.group(0).strip()})
    if periods:
        result["time_periods"] = periods

    return result


def process_contract(cba_id: int, *, verbose: bool = False) -> tuple[int, int]:
    """Extract values for all provisions in a contract. Returns (updated, total)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT provision_id, provision_text
                   FROM cba_provisions
                   WHERE cba_id = %s""",
                [cba_id],
            )
            provisions = cur.fetchall()

            if not provisions:
                if verbose:
                    print(f"  cba_id={cba_id}: no provisions found")
                return 0, 0

            updated = 0
            for prov_id, text in provisions:
                if not text:
                    continue
                values = extract_values(text)
                if values:
                    cur.execute(
                        "UPDATE cba_provisions SET extracted_values = %s WHERE provision_id = %s",
                        [json.dumps(values), prov_id],
                    )
                    updated += 1
                    if verbose:
                        cats = list(values.keys())
                        print(f"    provision_id={prov_id}: {cats}")

            conn.commit()

    if verbose:
        print(f"  cba_id={cba_id}: {updated}/{len(provisions)} provisions have extracted values")

    return updated, len(provisions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract structured values from provision text")
    parser.add_argument("--cba-id", type=int, help="Process specific cba_id (default: all)")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    args = parser.parse_args()

    with get_connection() as conn:
        with conn.cursor() as cur:
            if args.cba_id:
                cba_ids = [args.cba_id]
            else:
                cur.execute(
                    "SELECT DISTINCT cba_id FROM cba_provisions ORDER BY cba_id"
                )
                cba_ids = [row[0] for row in cur.fetchall()]

    if not cba_ids:
        print("No contracts with provisions found.")
        return

    print(f"Extracting values from {len(cba_ids)} contract(s)")
    print("=" * 60)

    total_updated = 0
    total_provisions = 0

    for cba_id in cba_ids:
        u, t = process_contract(cba_id, verbose=args.verbose)
        total_updated += u
        total_provisions += t

    pct = (total_updated / total_provisions * 100) if total_provisions else 0
    print(f"\nDone: {total_updated}/{total_provisions} provisions have extracted values ({pct:.1f}%)")


if __name__ == "__main__":
    main()
