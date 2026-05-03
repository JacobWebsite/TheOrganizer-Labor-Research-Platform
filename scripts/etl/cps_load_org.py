"""
Load IPUMS CPS ORG fixed-width extract into Postgres.

Reads the DDI XML codebook to parse variable layout, streams the .dat.gz file,
and COPYs into a TEXT staging table `cps_org_raw`. ORG filtering (EARNWT > 0)
happens at curate time, not here — we keep all records for demographic flexibility.

Usage:
  py scripts/etl/cps_load_org.py
  py scripts/etl/cps_load_org.py --extract-number 2 --max-lines 100000
"""
from __future__ import annotations

import argparse
import csv
import gzip
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
from db_config import get_connection  # noqa: E402

INPUT_DIR = PROJECT_ROOT / "New Data sources 2_27" / "cps_org"


def parse_args():
    ap = argparse.ArgumentParser(description="Load IPUMS CPS ORG extract into Postgres")
    ap.add_argument("--extract-number", type=int, default=None,
                    help="Extract number; defaults to value in .extract_number")
    ap.add_argument("--max-lines", type=int, default=0,
                    help="Limit lines loaded (0=all, for testing)")
    ap.add_argument("--copy-batch", type=int, default=1_000_000,
                    help="Lines per COPY batch (default 1M)")
    ap.add_argument("--keep-csv", action="store_true",
                    help="Keep intermediate CSV after load (default: delete)")
    return ap.parse_args()


def parse_ddi_layout(ddi_path: Path) -> list[tuple[str, int, int]]:
    """
    Parse IPUMS DDI 2.x XML and return [(name, start_pos_0indexed, end_pos_exclusive), ...]
    in declaration order.
    """
    tree = ET.parse(ddi_path)
    root = tree.getroot()
    # DDI uses ddi:codeBook namespace; tolerate both namespaced and bare tags
    ns = {"ddi": "ddi:codebook:2_5"}
    vars_iter = root.iter("{ddi:codebook:2_5}var")
    layout = []
    found = 0
    for v in vars_iter:
        found += 1
        name = v.attrib.get("name")
        loc = v.find("ddi:location", ns)
        if loc is None or not name:
            continue
        try:
            start = int(loc.attrib["StartPos"]) - 1  # 0-indexed
            end = int(loc.attrib["EndPos"])           # exclusive
        except (KeyError, ValueError):
            continue
        layout.append((name, start, end))
    if not layout:
        # Fallback: try without namespace
        for v in root.iter("var"):
            name = v.attrib.get("name")
            loc = v.find("location")
            if loc is None or not name:
                continue
            try:
                start = int(loc.attrib["StartPos"]) - 1
                end = int(loc.attrib["EndPos"])
            except (KeyError, ValueError):
                continue
            layout.append((name, start, end))
    if not layout:
        raise SystemExit(f"Could not parse any variables from DDI XML (found {found} <var> elements)")
    return layout


def write_csv(data_path: Path, out_csv: Path, layout: list[tuple[str, int, int]],
              max_lines: int) -> int:
    names = [n for n, _, _ in layout]
    rows = 0
    with gzip.open(data_path, "rt", encoding="utf-8", errors="replace") as f, \
         open(out_csv, "w", encoding="utf-8", newline="") as out:
        w = csv.writer(out)
        w.writerow(names)
        for line in f:
            rows += 1
            if max_lines and rows > max_lines:
                break
            cells = [line[s:e].strip() for _, s, e in layout]
            w.writerow(cells)
            if rows % 1_000_000 == 0:
                print(f"  parsed rows={rows:,}")
    return rows


def main():
    args = parse_args()

    # Locate extract
    if args.extract_number is not None:
        extract_n = args.extract_number
    else:
        marker = INPUT_DIR / ".extract_number"
        if not marker.exists():
            raise SystemExit(f"No extract number found at {marker}; pass --extract-number")
        extract_n = int(marker.read_text().strip())

    data_path = INPUT_DIR / f"cps_org_extract_{extract_n}.dat.gz"
    ddi_path = INPUT_DIR / f"cps_org_extract_{extract_n}.xml"
    if not data_path.exists() or not ddi_path.exists():
        raise SystemExit(f"Missing files: {data_path} or {ddi_path}")

    print(f"Loading extract #{extract_n}")
    print(f"  data: {data_path} ({data_path.stat().st_size/1024/1024:,.1f} MB)")
    print(f"  ddi:  {ddi_path}")

    layout = parse_ddi_layout(ddi_path)
    print(f"  parsed {len(layout)} variables from DDI:")
    for name, s, e in layout:
        print(f"    {name:12s}  {s+1:4d}-{e:4d}  width={e-s}")

    # Convert fixed-width to CSV (all-TEXT) for COPY
    out_csv = INPUT_DIR / f"cps_org_extract_{extract_n}.csv"
    print(f"\n  parsing fixed-width -> {out_csv.name}")
    rows = write_csv(data_path, out_csv, layout, args.max_lines)
    print(f"  wrote {rows:,} rows to {out_csv.name} ({out_csv.stat().st_size/1024/1024:,.1f} MB)")

    # Load into Postgres
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS cps_org_raw")
            cols_sql = ",\n  ".join(f'"{name.lower()}" TEXT' for name, _, _ in layout)
            cur.execute(f"""
                CREATE TABLE cps_org_raw (
                  {cols_sql},
                  _loaded_at TIMESTAMP DEFAULT NOW()
                )
            """)
            with open(out_csv, "r", encoding="utf-8", newline="") as fp:
                cur.copy_expert(
                    f"""
                    COPY cps_org_raw ({", ".join(f'"{n.lower()}"' for n, _, _ in layout)})
                    FROM STDIN WITH (FORMAT csv, HEADER true)
                    """,
                    fp,
                )
            cur.execute("SELECT COUNT(*) FROM cps_org_raw")
            db_rows = cur.fetchone()[0]
            cur.execute(
                "SELECT COUNT(*) FROM cps_org_raw "
                "WHERE earnwt IS NOT NULL AND earnwt::numeric > 0"
            )
            org_rows = cur.fetchone()[0]
        conn.commit()
        print(f"\nLoaded cps_org_raw -> {db_rows:,} total rows, {org_rows:,} ORG records (EARNWT>0)")
    finally:
        conn.close()

    if not args.keep_csv:
        out_csv.unlink()
        print(f"  deleted {out_csv.name}")


if __name__ == "__main__":
    main()
