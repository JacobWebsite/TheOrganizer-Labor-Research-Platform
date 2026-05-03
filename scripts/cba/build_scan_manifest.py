"""Build a manifest of every CBA PDF in a directory.

For each PDF records: page count, total text chars, count of low-text pages,
whether the document is classified as scanned, and any open-error.

Designed to run locally on CPU with pdfplumber (no OCR). Output is a CSV
written incrementally, so Ctrl+C is safe and re-running resumes where it
left off by reading the existing CSV first.

Usage (default paths match the OPDR CBAs archive in Downloads):
    py scripts/cba/build_scan_manifest.py
    py scripts/cba/build_scan_manifest.py --limit 20      # quick test
    py scripts/cba/build_scan_manifest.py --input DIR --output PATH
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

import pdfplumber

DEFAULT_INPUT = r"C:\Users\jakew\Downloads\OPDR CBAs"
DEFAULT_OUTPUT = (
    r"C:\Users\jakew\.local\bin\Labor Data Project_real\data\cba_scan_manifest.csv"
)

# Matches the scanned-document logic in scripts/cba/01_extract_text.py
SCANNED_THRESHOLD_CHARS = 100   # per page
SCANNED_THRESHOLD_RATIO = 0.5   # more than half the pages -> scanned

CSV_FIELDS = [
    "filename",
    "relative_path",
    "file_size_mb",
    "page_count",
    "scanned_pages",
    "total_chars",
    "avg_chars_per_page",
    "is_scanned",
    "error",
    "seconds",
]


def classify_pdf(path: Path) -> dict:
    """Open a PDF and return page-level text-density stats."""
    try:
        with pdfplumber.open(str(path)) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                return {
                    "page_count": 0,
                    "scanned_pages": 0,
                    "total_chars": 0,
                    "avg_chars_per_page": 0,
                    "is_scanned": True,
                    "error": "zero_pages",
                }

            total_chars = 0
            scanned_pages = 0
            for page in pdf.pages:
                # extract_text() (without layout) is fast and returns None or str
                txt = (page.extract_text() or "").strip()
                total_chars += len(txt)
                if len(txt) < SCANNED_THRESHOLD_CHARS:
                    scanned_pages += 1

            is_scanned = scanned_pages > page_count * SCANNED_THRESHOLD_RATIO
            return {
                "page_count": page_count,
                "scanned_pages": scanned_pages,
                "total_chars": total_chars,
                "avg_chars_per_page": total_chars // page_count,
                "is_scanned": is_scanned,
                "error": "",
            }
    except Exception as exc:  # noqa: BLE001 -- we want ANY failure recorded
        return {
            "page_count": 0,
            "scanned_pages": 0,
            "total_chars": 0,
            "avg_chars_per_page": 0,
            "is_scanned": False,
            "error": f"{type(exc).__name__}: {str(exc)[:150]}",
        }


def load_processed(output_path: Path) -> set[str]:
    """Read existing CSV (if any) and return the set of filenames already recorded."""
    if not output_path.exists():
        return set()
    seen: set[str] = set()
    with output_path.open("r", encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            seen.add(row["filename"])
    return seen


def print_summary(output_path: Path) -> None:
    """Print counts, scanned totals, and a cost estimate read back from the CSV."""
    with output_path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))

    total = len(rows)
    errors = [r for r in rows if r["error"]]
    scanned_rows = [r for r in rows if r["is_scanned"] == "1" and not r["error"]]
    text_rows = [r for r in rows if r["is_scanned"] == "0" and not r["error"]]

    scanned_pages_total = sum(int(r["page_count"]) for r in scanned_rows)
    text_pages_total = sum(int(r["page_count"]) for r in text_rows)

    avg_scanned_pages = scanned_pages_total / max(len(scanned_rows), 1)

    # Cost projections for downstream OCR planning
    # ADVERTISED GPU throughput for Docling is ~0.46s/page; we round up a bit.
    sec_per_page = 0.6
    gpu_hours = scanned_pages_total * sec_per_page / 3600
    cost_a4000 = gpu_hours * 0.20   # RunPod A4000 rate
    cost_3090 = gpu_hours * 0.35    # RunPod 3090 rate

    print("\n" + "=" * 68)
    print(f"MANIFEST SUMMARY  ({output_path.name})")
    print("=" * 68)
    print(f"  Total PDFs:           {total:,}")
    print(f"    text (extractable): {len(text_rows):,}   ({text_pages_total:,} pages)")
    print(f"    scanned:            {len(scanned_rows):,}   ({scanned_pages_total:,} pages)")
    print(f"    errors:             {len(errors):,}")
    if scanned_rows:
        print(f"  Avg scanned pages:    {avg_scanned_pages:.1f}")
        print(f"  Max scanned pages:    {max(int(r['page_count']) for r in scanned_rows):,}")
    print()
    print(f"  Projected OCR cost at {sec_per_page}s/page:")
    print(f"    Single A4000 (~$0.20/hr): {gpu_hours:.1f} GPU-hr  ->  ${cost_a4000:6.2f}")
    print(f"    Single 3090  (~$0.35/hr): {gpu_hours:.1f} GPU-hr  ->  ${cost_3090:6.2f}")
    if errors:
        print()
        print("  First 5 errors:")
        for r in errors[:5]:
            print(f"    {r['filename'][:60]:60s}  {r['error']}")
    print("=" * 68)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default=DEFAULT_INPUT, help="Directory of PDFs")
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Output CSV path")
    parser.add_argument("--limit", type=int, default=None, help="Max files to process")
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Print summary of existing CSV without processing any PDFs.",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if args.summary_only:
        if not output_path.exists():
            print(f"No manifest at {output_path} yet.")
            sys.exit(1)
        print_summary(output_path)
        return

    input_dir = Path(args.input)
    if not input_dir.exists():
        print(f"ERROR: input directory not found: {input_dir}")
        sys.exit(1)

    pdfs = sorted(input_dir.rglob("*.pdf"))
    if args.limit is not None:
        pdfs = pdfs[: args.limit]
    total = len(pdfs)
    print(f"Found {total:,} PDFs under {input_dir}")

    processed = load_processed(output_path)
    if processed:
        print(f"  resume: {len(processed):,} already in {output_path.name}")

    remaining = [p for p in pdfs if p.name not in processed]
    print(f"  to process: {len(remaining):,}")
    if not remaining:
        print_summary(output_path)
        return

    write_header = not output_path.exists()
    start_wall = time.time()

    with output_path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if write_header:
            writer.writeheader()

        for idx, pdf_path in enumerate(remaining, start=1):
            t0 = time.time()
            size_mb = pdf_path.stat().st_size / (1024 * 1024)
            rel = pdf_path.relative_to(input_dir).as_posix()

            res = classify_pdf(pdf_path)
            elapsed = time.time() - t0

            writer.writerow({
                "filename": pdf_path.name,
                "relative_path": rel,
                "file_size_mb": round(size_mb, 2),
                "page_count": res["page_count"],
                "scanned_pages": res["scanned_pages"],
                "total_chars": res["total_chars"],
                "avg_chars_per_page": res["avg_chars_per_page"],
                "is_scanned": int(res["is_scanned"]),
                "error": res["error"],
                "seconds": round(elapsed, 2),
            })
            fh.flush()

            if idx % 25 == 0 or idx == len(remaining):
                wall = time.time() - start_wall
                rate = idx / max(wall, 0.001)
                eta_min = (len(remaining) - idx) / max(rate, 0.01) / 60
                tag = (
                    "ERROR" if res["error"]
                    else "SCANNED" if res["is_scanned"]
                    else "text"
                )
                name = pdf_path.name[:52]
                print(
                    f"  [{idx:4d}/{len(remaining):4d}]  "
                    f"{rate:4.1f} PDF/s  ETA {eta_min:5.1f} min   "
                    f"{res['page_count']:4d}p {tag:<8s}  {name}"
                )

    print_summary(output_path)


if __name__ == "__main__":
    main()
