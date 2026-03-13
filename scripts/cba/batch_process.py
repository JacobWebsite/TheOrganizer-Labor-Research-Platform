"""Batch processor for CBA PDFs.

Scans a configurable inbox folder for .pdf files, deduplicates by SHA-256 hash,
processes each through the full CBA pipeline (extract text -> extract parties ->
find articles -> tag provisions), and moves processed files to a completed folder.

Usage:
    py scripts/cba/batch_process.py [--inbox data/cba_inbox] [--processed data/cba_processed]
    py scripts/cba/batch_process.py --dry-run
    py scripts/cba/batch_process.py --min-confidence 0.60
"""
from __future__ import annotations

import argparse
import importlib
import logging
import re
import shutil
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

# Pipeline modules (imported lazily to let sys.path take effect)
_s1 = importlib.import_module("scripts.cba.01_extract_text")
_s2 = importlib.import_module("scripts.cba.02_extract_parties")
_s3 = importlib.import_module("scripts.cba.03_find_articles")
_s4 = importlib.import_module("scripts.cba.04_tag_category")
from scripts.cba.rule_engine import match_text_all_categories, populate_context

PROJECT_ROOT = Path(__file__).resolve().parents[2]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("cba_batch")


# ---------------------------------------------------------------------------
# Status helpers
# ---------------------------------------------------------------------------

def _set_status(cba_id: int, status: str, error: str | None = None) -> None:
    """Update processing_status (and optionally processing_error) on cba_documents."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if error:
                cur.execute(
                    "UPDATE cba_documents SET processing_status = %s, processing_error = %s, updated_at = NOW() WHERE cba_id = %s",
                    [status, error[:2000], cba_id],
                )
            else:
                cur.execute(
                    "UPDATE cba_documents SET processing_status = %s, processing_error = NULL, updated_at = NOW() WHERE cba_id = %s",
                    [status, cba_id],
                )
            conn.commit()


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

def _hash_exists(file_hash: str) -> int | None:
    """Check if a file hash already exists in cba_documents. Returns cba_id or None."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cba_id FROM cba_documents WHERE file_hash = %s LIMIT 1",
                [file_hash],
            )
            row = cur.fetchone()
            return row[0] if row else None


# ---------------------------------------------------------------------------
# Filename parsing
# ---------------------------------------------------------------------------

_FILENAME_PATTERNS = [
    # "Employer - Union.pdf" or "Employer -- Union.pdf"
    re.compile(r"^(.+?)\s*[-]{1,2}\s+(.+?)\.pdf$", re.IGNORECASE),
]


def _parse_filename(filename: str) -> tuple[str, str]:
    """Try to extract employer and union from the filename.

    Returns (employer, union). Falls back to (filename_stem, 'Unknown').
    """
    for pattern in _FILENAME_PATTERNS:
        m = pattern.match(filename)
        if m:
            employer = m.group(1).strip()
            union = m.group(2).strip()
            if employer and union:
                return employer, union

    # Fallback: use filename stem as employer (replace underscores with spaces)
    stem = Path(filename).stem.replace("_", " ").strip()
    return stem or "Unknown", "Unknown"


# ---------------------------------------------------------------------------
# Per-file pipeline
# ---------------------------------------------------------------------------

def process_single_file(
    pdf_path: Path,
    *,
    min_confidence: float = 0.50,
    dry_run: bool = False,
) -> dict:
    """Process a single PDF through the full CBA pipeline.

    Returns a result dict with keys: cba_id, status, provisions, error.
    """
    result = {"file": pdf_path.name, "cba_id": None, "status": "failed", "provisions": 0, "error": None}

    # --- Compute hash and check for duplicates ---
    file_hash = _s1.compute_file_hash(pdf_path)
    existing_id = _hash_exists(file_hash)
    if existing_id:
        result["status"] = "duplicate"
        result["cba_id"] = existing_id
        result["error"] = f"Duplicate of cba_id={existing_id}"
        log.info("  SKIP (duplicate of cba_id=%d): %s", existing_id, pdf_path.name)
        return result

    # --- Parse employer/union from filename ---
    employer, union = _parse_filename(pdf_path.name)
    log.info("  Employer: %s | Union: %s", employer, union)

    cba_id = None
    try:
        # --- Stage 1: Extract text (with OCR fallback) ---
        log.info("  Stage 1: Extracting text...")
        doc, ext_method = _s1.load_pdf_text_with_ocr(pdf_path)
        cba_id = _s1.insert_document(
            employer_name=employer,
            union_name=union,
            doc=doc,
            file_path=str(pdf_path),
            file_hash=file_hash,
            extraction_method=ext_method,
        )
        result["cba_id"] = cba_id
        _set_status(cba_id, "extracting")
        log.info("    cba_id=%d, pages=%d, chars=%d, method=%s", cba_id, doc.page_count, len(doc.text), ext_method)

        if ext_method == "ocr":
            quality = _s1.ocr_quality_score(doc.text)
            log.info("    OCR quality: %.1f%% (%s)", quality * 100, _s1._quality_label(quality))
        elif _s1.is_scanned_document(doc):
            log.warning("    Document appears scanned (%d chars, %d pages) -- OCR not available", len(doc.text.strip()), doc.page_count)

        # --- Stage 2: Extract parties ---
        log.info("  Stage 2: Extracting parties/metadata...")
        _set_status(cba_id, "parsed")
        meta = _s2.extract_parties_from_text(doc.text)
        _s2.update_document_metadata(cba_id, meta)

        # Entity linking
        _s2.link_entities(cba_id, employer, union)
        log.info("    Employer: %s, Union: %s", meta.employer_name or "(not found)", meta.union_name or "(not found)")

        # --- Stage 3: Find articles ---
        log.info("  Stage 3: Finding article structure...")
        chunks = _s3.find_articles(doc.text, doc.spans)
        _s3.save_structure(cba_id, chunks)
        log.info("    Found %d headings", len(chunks))

        # --- Stage 4: Tag provisions ---
        log.info("  Stage 4: Tagging provisions...")
        _set_status(cba_id, "tagged")
        matches = match_text_all_categories(chunks, min_confidence=min_confidence)
        populate_context(matches, doc.text)
        log.info("    Found %d provisions", len(matches))

        if not dry_run and matches:
            spans = doc.spans
            inserted = _s4.insert_provisions(cba_id, matches, spans)
            log.info("    Inserted %d provisions", inserted)

            with get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE cba_documents SET extraction_status = 'completed', updated_at = NOW() WHERE cba_id = %s",
                        [cba_id],
                    )
                    conn.commit()

        # --- Mark completed ---
        _set_status(cba_id, "completed")
        result["status"] = "completed"
        result["provisions"] = len(matches)

    except Exception as exc:
        error_msg = f"{type(exc).__name__}: {exc}"
        log.error("  FAILED: %s", error_msg)
        result["error"] = error_msg
        if cba_id:
            _set_status(cba_id, "failed", error_msg)

    return result


# ---------------------------------------------------------------------------
# Batch orchestrator
# ---------------------------------------------------------------------------

def run_batch(
    inbox: Path,
    processed: Path,
    *,
    min_confidence: float = 0.50,
    dry_run: bool = False,
) -> list[dict]:
    """Scan inbox for PDFs and process each through the pipeline."""
    if not inbox.exists():
        log.info("Creating inbox directory: %s", inbox)
        inbox.mkdir(parents=True, exist_ok=True)

    processed.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(inbox.glob("*.pdf"))
    if not pdf_files:
        log.info("No PDF files found in %s", inbox)
        return []

    log.info("Found %d PDF(s) in %s", len(pdf_files), inbox)
    if dry_run:
        log.info("DRY RUN MODE: provisions will not be inserted, files will not be moved")

    results = []
    for i, pdf_path in enumerate(pdf_files, 1):
        log.info("")
        log.info("[%d/%d] Processing: %s", i, len(pdf_files), pdf_path.name)
        log.info("-" * 60)

        result = process_single_file(pdf_path, min_confidence=min_confidence, dry_run=dry_run)
        results.append(result)

        # Move processed file (unless dry run or duplicate)
        if not dry_run and result["status"] in ("completed", "duplicate"):
            dest = processed / pdf_path.name
            # Handle name collision
            if dest.exists():
                stem = dest.stem
                suffix = dest.suffix
                counter = 1
                while dest.exists():
                    dest = processed / f"{stem}_{counter}{suffix}"
                    counter += 1
            shutil.move(str(pdf_path), str(dest))
            log.info("  Moved to: %s", dest)

    # --- Summary ---
    log.info("")
    log.info("=" * 60)
    log.info("BATCH SUMMARY")
    log.info("=" * 60)

    status_counts = Counter(r["status"] for r in results)
    total_provisions = sum(r["provisions"] for r in results)

    for status, count in status_counts.most_common():
        log.info("  %s: %d", status, count)
    log.info("  Total provisions: %d", total_provisions)
    log.info("")

    # Log failures
    failures = [r for r in results if r["status"] == "failed"]
    if failures:
        log.info("FAILURES:")
        for r in failures:
            log.info("  %s: %s", r["file"], r["error"])

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Batch process CBA PDFs")
    parser.add_argument(
        "--inbox", default="data/cba_inbox",
        help="Input folder with PDF files (default: data/cba_inbox)",
    )
    parser.add_argument(
        "--processed", default="data/cba_processed",
        help="Output folder for processed files (default: data/cba_processed)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Process without inserting provisions or moving files")
    parser.add_argument("--min-confidence", type=float, default=0.50, help="Minimum confidence threshold (default: 0.50)")
    args = parser.parse_args()

    inbox = (PROJECT_ROOT / args.inbox).resolve()
    processed = (PROJECT_ROOT / args.processed).resolve()

    log.info("CBA Batch Processor")
    log.info("  Inbox:     %s", inbox)
    log.info("  Processed: %s", processed)
    log.info("  Min conf:  %.2f", args.min_confidence)
    log.info("  Dry run:   %s", args.dry_run)

    results = run_batch(inbox, processed, min_confidence=args.min_confidence, dry_run=args.dry_run)

    # Exit code: 0 if all succeeded or duplicates, 1 if any failures
    failures = [r for r in results if r["status"] == "failed"]
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
