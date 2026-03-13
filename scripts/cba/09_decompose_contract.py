"""Script 9: Orchestrator for progressive contract decomposition.

Runs the full decomposition pipeline (Pass 2 + Pass 3) or individual steps.

Usage:
    py scripts/cba/09_decompose_contract.py --cba-id 26                    # Full pipeline
    py scripts/cba/09_decompose_contract.py --cba-id 26 --pass 2           # Just Pass 2 (TOC + split)
    py scripts/cba/09_decompose_contract.py --cba-id 26 --pass 3           # Just Pass 3 (enrich)
    py scripts/cba/09_decompose_contract.py --cba-id 26 --with-images      # Include page images
    py scripts/cba/09_decompose_contract.py --pdf "path/to/new.pdf"        # New contract from scratch
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection


def run_pipeline(
    cba_id: int,
    *,
    pass_num: int | None = None,
    with_images: bool = False,
    image_pages: str | None = None,
    verbose: bool = False,
) -> None:
    """Run the decomposition pipeline on an existing cba_id."""

    # Verify document exists with full_text
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_text IS NOT NULL, page_count, decomposition_status "
                "FROM cba_documents WHERE cba_id = %s",
                [cba_id],
            )
            row = cur.fetchone()
            if not row:
                print(f"ERROR: cba_id={cba_id} not found")
                sys.exit(1)
            has_text, page_count, status = row
            if not has_text:
                print(f"ERROR: cba_id={cba_id} has no full_text. Run 01+02 first.")
                sys.exit(1)

    print(f"Decomposing cba_id={cba_id} (pages={page_count}, status={status})")
    print("=" * 60)

    should_run_pass2 = pass_num is None or pass_num == 2
    should_run_pass3 = pass_num is None or pass_num == 3

    # --- Pass 2: TOC Parse + Section Split ---
    if should_run_pass2:
        print("\nPASS 2a: Parsing Table of Contents")
        print("-" * 40)
        _s5 = importlib.import_module("scripts.cba.05_parse_toc")
        # Load text for parsing
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT full_text FROM cba_documents WHERE cba_id = %s",
                    [cba_id],
                )
                text = cur.fetchone()[0]

        entries = _s5.parse_toc(text, verbose=verbose)

        if not entries:
            print("  No TOC found. Falling back to heading heuristic...")
            _art_mod = importlib.import_module("scripts.cba.03_find_articles")
            find_articles = _art_mod.find_articles
            get_document_data = _art_mod.get_document_data
            text2, spans = get_document_data(cba_id)
            if text2:
                chunks = find_articles(text2, spans)
                from scripts.cba.models import TOCEntry
                entries = [
                    TOCEntry(
                        number=c.number,
                        title=c.title,
                        page_number=c.page_start or 0,
                        level=c.level,
                        parent_number=c.parent_number,
                    )
                    for c in chunks
                ]

        if entries:
            _s5.save_toc(cba_id, entries)
            articles = [e for e in entries if e.level == 1]
            subs = [e for e in entries if e.level >= 2]
            print(f"  Parsed {len(entries)} TOC entries: {len(articles)} articles + {len(subs)} sub-sections")
        else:
            print("  WARNING: No TOC or headings found.")
            if should_run_pass3:
                print("  Skipping section split and enrichment.")
            return

        print("\nPASS 2b: Splitting into sections")
        print("-" * 40)
        _s6 = importlib.import_module("scripts.cba.06_split_sections")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT full_text, page_count FROM cba_documents WHERE cba_id = %s",
                    [cba_id],
                )
                text, page_count = cur.fetchone()

        spans = _s6.reconstruct_spans(text, page_count)
        sections = _s6.split_sections(text, spans, entries, verbose=verbose)

        if sections:
            inserted = _s6.insert_sections(cba_id, sections)
            total_chars = sum(s.char_end - s.char_start for s in sections)
            coverage = total_chars / len(text) * 100
            print(f"  Created {inserted} sections ({coverage:.1f}% text coverage)")
        else:
            print("  WARNING: No sections created.")
            return

    # --- Page images (optional) ---
    if with_images:
        print("\nEXTRACTING PAGE IMAGES")
        print("-" * 40)
        _s7 = importlib.import_module("scripts.cba.07_extract_page_images")

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT file_path FROM cba_documents WHERE cba_id = %s",
                    [cba_id],
                )
                pdf_path = cur.fetchone()[0]

        if image_pages:
            pages = _s7.parse_page_range(image_pages)
        else:
            pages = _s7.detect_wage_table_pages(cba_id)

        if pages:
            images = _s7.extract_page_images(pdf_path, cba_id, pages, verbose=verbose)
            _s7.insert_page_images(images)
            _s7.link_images_to_sections(cba_id)
            print(f"  Extracted {len(images)} page images")
        else:
            print("  No pages to extract.")

    # --- Pass 3: Enrichment ---
    if should_run_pass3:
        print("\nPASS 3: Enriching sections")
        print("-" * 40)
        _s8 = importlib.import_module("scripts.cba.08_enrich_sections")
        enriched = _s8.enrich_sections(cba_id, verbose=verbose)
        print(f"  Enriched {enriched} sections")

    # Update final status
    final_status = "enriched" if should_run_pass3 else "sections_split"
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cba_documents SET decomposition_status = %s, updated_at = NOW() WHERE cba_id = %s",
                [final_status, cba_id],
            )
            conn.commit()

    print("\n" + "=" * 60)
    print("DECOMPOSITION COMPLETE")
    print(f"  cba_id={cba_id}, status={final_status}")
    print("=" * 60)


def run_from_pdf(
    pdf_path: str,
    *,
    employer: str | None = None,
    union: str | None = None,
    with_images: bool = False,
    verbose: bool = False,
) -> int:
    """Process a new PDF from scratch: extract text, then decompose."""
    pdf = Path(pdf_path).resolve()
    if not pdf.exists():
        print(f"ERROR: PDF not found: {pdf}")
        sys.exit(1)

    # Infer names from filename if not provided
    if not employer or not union:
        stem = pdf.stem
        if " - " in stem:
            parts = stem.split(" - ", 1)
            employer = employer or parts[0].strip()
            union = union or parts[1].strip()
        else:
            employer = employer or stem
            union = union or "Unknown"

    print(f"Processing new PDF: {pdf.name}")
    print(f"  Employer: {employer}")
    print(f"  Union: {union}")

    # Step 1: Extract text
    print("\n" + "=" * 60)
    print("STEP 1: Extracting text")
    print("=" * 60)
    _s1 = importlib.import_module("scripts.cba.01_extract_text")
    doc, ext_method = _s1.load_pdf_text_with_ocr(pdf)
    print(f"  {doc.page_count} pages, {len(doc.text):,} chars ({ext_method})")

    cba_id = _s1.insert_document(
        employer_name=employer,
        union_name=union,
        doc=doc,
        file_path=str(pdf),
        extraction_method=ext_method,
    )
    print(f"  Inserted as cba_id={cba_id}")

    # Step 2: Extract parties
    print("\n" + "=" * 60)
    print("STEP 2: Extracting metadata")
    print("=" * 60)
    _s2 = importlib.import_module("scripts.cba.02_extract_parties")
    meta = _s2.extract_parties_from_text(doc.text)
    _s2.update_document_metadata(cba_id, meta)
    print(f"  Employer: {meta.employer_name or '(not found)'}")
    print(f"  Union: {meta.union_name or '(not found)'}")

    # Steps 3+: Decompose
    run_pipeline(cba_id, with_images=with_images, verbose=verbose)
    return cba_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Progressive contract decomposition")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--cba-id", type=int, help="Process existing cba_id")
    group.add_argument("--pdf", help="Process new PDF from scratch")
    parser.add_argument("--employer", help="Employer name (for --pdf mode)")
    parser.add_argument("--union", help="Union name (for --pdf mode)")
    parser.add_argument("--pass", type=int, dest="pass_num", choices=[2, 3],
                        help="Run only a specific pass (2=TOC+split, 3=enrich)")
    parser.add_argument("--with-images", action="store_true",
                        help="Extract page images for wage tables")
    parser.add_argument("--image-pages", help="Specific pages to image (e.g., '139-142')")
    parser.add_argument("--verbose", action="store_true", help="Detailed output")
    args = parser.parse_args()

    if args.pdf:
        run_from_pdf(
            args.pdf,
            employer=args.employer,
            union=args.union,
            with_images=args.with_images,
            verbose=args.verbose,
        )
    else:
        run_pipeline(
            args.cba_id,
            pass_num=args.pass_num,
            with_images=args.with_images,
            image_pages=args.image_pages,
            verbose=args.verbose,
        )


if __name__ == "__main__":
    main()
