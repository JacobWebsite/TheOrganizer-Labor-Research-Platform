"""Script 1: Extract text from a CBA PDF and store in the database.

Reuses pdfplumber extraction logic from cba_processor.py.
Populates cba_documents.full_text so we never need to re-process the PDF.

Usage:
    py scripts/cba/01_extract_text.py --pdf "path/to/file.pdf" --employer "..." --union "..."
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

import pdfplumber

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import DocumentText, PageSpan


def load_pdf_text(pdf_path: Path, *, max_pages: int | None = None) -> DocumentText:
    """Extract text from a PDF with per-page character offsets."""
    spans: list[PageSpan] = []
    chunks: list[str] = []
    cursor = 0

    with pdfplumber.open(str(pdf_path)) as pdf:
        for idx, page in enumerate(pdf.pages, start=1):
            if max_pages is not None and idx > max_pages:
                break
            page_text = page.extract_text(layout=True) or ""
            if page_text and not page_text.endswith("\n"):
                page_text += "\n"
            start = cursor
            chunks.append(page_text)
            cursor += len(page_text)
            spans.append(PageSpan(page_number=idx, char_start=start, char_end=cursor))

        return DocumentText(text="".join(chunks), page_count=len(pdf.pages), spans=spans)


def is_scanned_document(doc: DocumentText) -> bool:
    """Heuristic: < 80 chars/page = scanned."""
    if doc.page_count == 0:
        return True
    avg_chars = len(doc.text.strip()) / max(doc.page_count, 1)
    return avg_chars < 80


def page_for_char(spans: list[PageSpan], char_pos: int) -> int | None:
    """Binary search to map a character offset to a page number."""
    lo, hi = 0, len(spans) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        span = spans[mid]
        if char_pos < span.char_start:
            hi = mid - 1
        elif char_pos >= span.char_end:
            lo = mid + 1
        else:
            return span.page_number
    return None


def parse_date(s: str | None) -> date | None:
    """Try to parse a date string in common formats."""
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%B %d, %Y", "%b %d, %Y"):
        try:
            return datetime.strptime(s.strip(), fmt).date()
        except ValueError:
            continue
    return None


def insert_document(
    *,
    employer_name: str,
    union_name: str,
    doc: DocumentText,
    file_path: str,
    source_name: str = "Local Archive",
    source_url: str | None = None,
    effective_date: date | None = None,
    expiration_date: date | None = None,
) -> int:
    """Insert a new CBA document record and return cba_id."""
    scanned = is_scanned_document(doc)
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cba_documents (
                    employer_name_raw, union_name_raw,
                    source_name, source_url, file_path, file_format,
                    is_scanned, page_count,
                    effective_date, expiration_date,
                    is_current, structure_quality, ocr_status,
                    extraction_status, extraction_method, full_text
                )
                VALUES (%s, %s, %s, %s, %s, 'PDF', %s, %s, %s, %s,
                        TRUE, %s, %s, %s, 'rule_engine', %s)
                RETURNING cba_id
                """,
                [
                    employer_name, union_name,
                    source_name, source_url or f"local://{Path(file_path).name}",
                    file_path, scanned, doc.page_count,
                    effective_date, expiration_date,
                    "well-organized",
                    "needed" if scanned else "not_needed",
                    "needs_ocr" if scanned else "pending",
                    doc.text,
                ],
            )
            cba_id = int(cur.fetchone()[0])
            conn.commit()
    return cba_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract text from a CBA PDF")
    parser.add_argument("--pdf", required=True, help="Path to PDF file")
    parser.add_argument("--employer", required=True, help="Employer name")
    parser.add_argument("--union", required=True, help="Union name")
    parser.add_argument("--source", default="Local Archive", help="Source name")
    parser.add_argument("--effective-date", default=None, help="Effective date (YYYY-MM-DD)")
    parser.add_argument("--expiration-date", default=None, help="Expiration date (YYYY-MM-DD)")
    parser.add_argument("--max-pages", type=int, default=None, help="Limit pages extracted")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Extracting text from: {pdf_path.name}")
    doc = load_pdf_text(pdf_path, max_pages=args.max_pages)

    if is_scanned_document(doc):
        print(f"  WARNING: Document appears to be scanned ({len(doc.text.strip())} chars, {doc.page_count} pages)")

    print(f"  Pages: {doc.page_count}")
    print(f"  Characters: {len(doc.text):,}")
    print(f"  Avg chars/page: {len(doc.text.strip()) / max(doc.page_count, 1):.0f}")

    cba_id = insert_document(
        employer_name=args.employer,
        union_name=args.union,
        doc=doc,
        file_path=str(pdf_path),
        source_name=args.source,
        effective_date=parse_date(args.effective_date),
        expiration_date=parse_date(args.expiration_date),
    )

    print(f"\n  Inserted as cba_id = {cba_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
