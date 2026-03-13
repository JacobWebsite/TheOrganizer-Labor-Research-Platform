"""Script 1: Extract text from a CBA PDF and store in the database.

Reuses pdfplumber extraction logic from cba_processor.py.
Populates cba_documents.full_text so we never need to re-process the PDF.

Usage:
    py scripts/cba/01_extract_text.py --pdf "path/to/file.pdf" --employer "..." --union "..."
"""
from __future__ import annotations

import argparse
import hashlib
import re
import sys
from datetime import date, datetime
from pathlib import Path

import pdfplumber

# OCR support: optional dependency
try:
    import pytesseract
    from PIL import Image
    HAS_OCR = True
except ImportError:
    HAS_OCR = False

# Allow running from project root
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import DocumentText, PageSpan

# Common English words for OCR quality estimation
_COMMON_WORDS = frozenset(
    "the be to of and a in that have i it for not on with he as you do at "
    "this but his by from they we say her she or an will my one all would "
    "there their what so up out if about who get which go me when make can "
    "like time no just him know take people into year your good some could "
    "them see other than then now look only come its over think also back "
    "after use two how our work first well way even new want because any "
    "these give day most us shall may must not employee employer union "
    "agreement contract article section party parties shall company "
    "workers members local board labor management seniority wages hours "
    "grievance arbitration overtime benefits insurance health pension "
    "vacation sick leave holidays schedule pay rate classification "
    "probationary discipline discharge termination layoff recall ".split()
)


def compute_file_hash(file_path: Path) -> str:
    """Compute SHA-256 hash of a file."""
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


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
    """Detect scanned documents by checking per-page character yield.

    A page with fewer than 100 non-whitespace characters is considered scanned.
    If more than half the pages are scanned, the document is classified as scanned.
    """
    if doc.page_count == 0:
        return True

    scanned_pages = 0
    for span in doc.spans:
        page_text = doc.text[span.char_start:span.char_end]
        non_ws = len(page_text.strip())
        if non_ws < 100:
            scanned_pages += 1

    # If majority of pages are low-text, treat as scanned
    return scanned_pages > doc.page_count / 2


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


def ocr_quality_score(text: str) -> float:
    """Estimate OCR text quality as fraction of recognized dictionary words.

    Returns a score between 0.0 (gibberish) and 1.0 (perfect).
    """
    words = re.findall(r"[a-zA-Z]{2,}", text.lower())
    if not words:
        return 0.0
    recognized = sum(1 for w in words if w in _COMMON_WORDS)
    return recognized / len(words)


def _quality_label(score: float) -> str:
    """Map a quality score to a human-readable label."""
    if score >= 0.30:
        return "well-organized"
    elif score >= 0.15:
        return "moderate"
    else:
        return "poor"


def ocr_pdf(pdf_path: Path, *, max_pages: int | None = None) -> DocumentText:
    """OCR a scanned PDF using pytesseract, returning DocumentText.

    Requires pytesseract and Pillow. Raises RuntimeError if not available.
    """
    if not HAS_OCR:
        raise RuntimeError(
            "OCR not available: install pytesseract and Pillow "
            "(pip install pytesseract Pillow) and ensure Tesseract is on PATH"
        )

    spans: list[PageSpan] = []
    chunks: list[str] = []
    cursor = 0

    # pdf2image or pdfplumber page-to-image conversion
    # Use pdfplumber's page.to_image() which is always available
    with pdfplumber.open(str(pdf_path)) as pdf:
        total_pages = len(pdf.pages)
        for idx, page in enumerate(pdf.pages, start=1):
            if max_pages is not None and idx > max_pages:
                break
            # Convert page to image for OCR
            img = page.to_image(resolution=300)
            pil_image = img.original  # PIL Image
            page_text = pytesseract.image_to_string(pil_image) or ""
            if page_text and not page_text.endswith("\n"):
                page_text += "\n"
            start = cursor
            chunks.append(page_text)
            cursor += len(page_text)
            spans.append(PageSpan(page_number=idx, char_start=start, char_end=cursor))

    return DocumentText(text="".join(chunks), page_count=total_pages, spans=spans)


def load_pdf_text_with_ocr(
    pdf_path: Path, *, max_pages: int | None = None
) -> tuple[DocumentText, str]:
    """Extract text from a PDF, falling back to OCR if scanned.

    Returns (DocumentText, extraction_method) where extraction_method is
    'pdfplumber' or 'ocr'.
    """
    doc = load_pdf_text(pdf_path, max_pages=max_pages)

    if not is_scanned_document(doc):
        return doc, "pdfplumber"

    # Attempt OCR fallback
    if not HAS_OCR:
        # Return the sparse pdfplumber text as-is
        return doc, "pdfplumber"

    ocr_doc = ocr_pdf(pdf_path, max_pages=max_pages)
    return ocr_doc, "ocr"


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
    file_hash: str | None = None,
    extraction_method: str | None = None,
) -> int:
    """Insert a new CBA document record and return cba_id."""
    scanned = is_scanned_document(doc)
    # Compute hash if not provided and file exists
    if file_hash is None:
        p = Path(file_path)
        if p.exists():
            file_hash = compute_file_hash(p)

    # Determine extraction_method and ocr_status
    ext_method = extraction_method or "rule_engine"
    if ext_method == "ocr":
        ocr_status = "completed"
    elif scanned:
        ocr_status = "needed"
    else:
        ocr_status = "not_needed"

    # Compute quality score for OCR text
    quality = ocr_quality_score(doc.text) if ext_method == "ocr" else None
    structure_quality = _quality_label(quality) if quality is not None else "well-organized"

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
                    extraction_status, extraction_method, full_text,
                    file_hash
                )
                VALUES (%s, %s, %s, %s, %s, 'PDF', %s, %s, %s, %s,
                        TRUE, %s, %s, %s, %s, %s, %s)
                RETURNING cba_id
                """,
                [
                    employer_name, union_name,
                    source_name, source_url or f"local://{Path(file_path).name}",
                    file_path, scanned, doc.page_count,
                    effective_date, expiration_date,
                    structure_quality,
                    ocr_status,
                    "needs_ocr" if (scanned and ext_method != "ocr") else "pending",
                    ext_method,
                    doc.text,
                    file_hash,
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
    parser.add_argument("--no-ocr", action="store_true", help="Disable OCR fallback")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    print(f"Extracting text from: {pdf_path.name}")

    if args.no_ocr:
        doc = load_pdf_text(pdf_path, max_pages=args.max_pages)
        ext_method = "pdfplumber"
    else:
        doc, ext_method = load_pdf_text_with_ocr(pdf_path, max_pages=args.max_pages)

    scanned = is_scanned_document(doc)
    if scanned and ext_method != "ocr":
        print(f"  WARNING: Document appears scanned ({len(doc.text.strip())} chars, {doc.page_count} pages)")
        if not HAS_OCR:
            print("  NOTE: pytesseract not installed -- OCR not available")
    elif ext_method == "ocr":
        quality = ocr_quality_score(doc.text)
        print(f"  OCR completed: quality={quality:.1%} ({_quality_label(quality)})")

    print(f"  Extraction method: {ext_method}")
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
        extraction_method=ext_method,
    )

    print(f"\n  Inserted as cba_id = {cba_id}")
    print("  Done.")


if __name__ == "__main__":
    main()
