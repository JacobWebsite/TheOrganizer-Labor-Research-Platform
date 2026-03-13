"""Orchestrator: Run the full CBA rule-engine pipeline on a contract.

Executes Scripts 1 -> 2 -> 3 -> 4 in sequence.

Usage:
    py scripts/cba/process_contract.py --pdf "path/to/file.pdf" --employer "..." --union "..."
    py scripts/cba/process_contract.py --pdf "..." --employer "..." --union "..." --dry-run
    py scripts/cba/process_contract.py --pdf "..." --employer "..." --union "..." --categories healthcare,wages
"""
from __future__ import annotations

import argparse
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.cba.models import PageSpan


def main() -> None:
    parser = argparse.ArgumentParser(description="Process a CBA contract through the full pipeline")
    parser.add_argument("--pdf", required=False, help="Path to PDF file (required unless --reprocess)")
    parser.add_argument("--employer", required=False, help="Employer name (required unless --reprocess)")
    parser.add_argument("--union", required=False, help="Union name (required unless --reprocess)")
    parser.add_argument("--source", default="Local Archive", help="Source name")
    parser.add_argument("--effective-date", default=None, help="Effective date (YYYY-MM-DD)")
    parser.add_argument("--expiration-date", default=None, help="Expiration date (YYYY-MM-DD)")
    parser.add_argument("--categories", default=None, help="Comma-separated categories (default: all)")
    parser.add_argument("--dry-run", action="store_true", help="Don't insert provisions (dry-run mode)")
    parser.add_argument("--min-confidence", type=float, default=0.50, help="Minimum confidence threshold")
    parser.add_argument("--reprocess", type=int, default=None, metavar="CBA_ID",
                        help="Re-process an existing cba_id (deletes old provisions, re-runs pipeline)")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output")
    args = parser.parse_args()

    # --- Validate required args for non-reprocess mode ---
    if not args.reprocess and (not args.pdf or not args.employer or not args.union):
        parser.error("--pdf, --employer, and --union are required unless --reprocess is used")

    # --- Reprocess mode ---
    if args.reprocess:
        cba_id = args.reprocess
        print(f"Re-processing cba_id={cba_id}")
        from db_config import get_connection as _gc
        with _gc() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT full_text, page_count, employer_name_raw, union_name_raw, file_path FROM cba_documents WHERE cba_id = %s", [cba_id])
                row = cur.fetchone()
                if not row:
                    print(f"ERROR: cba_id={cba_id} not found")
                    sys.exit(1)
                full_text, page_count, emp_name, union_name_raw, file_path = row

                # Delete old provisions
                cur.execute("DELETE FROM cba_provisions WHERE cba_id = %s", [cba_id])
                deleted = cur.rowcount
                print(f"  Deleted {deleted} old provisions")

                # Reset status
                cur.execute(
                    "UPDATE cba_documents SET extraction_status = 'pending', extraction_method = 'rule_engine', updated_at = NOW() WHERE cba_id = %s",
                    [cba_id],
                )
                conn.commit()

        from scripts.cba.models import DocumentText

        if full_text:
            # Reconstruct DocumentText from stored text
            chars_per_page = len(full_text) // max(page_count or 1, 1)
            spans = []
            for i in range(page_count or 1):
                spans.append(PageSpan(
                    page_number=i + 1,
                    char_start=i * chars_per_page,
                    char_end=min((i + 1) * chars_per_page, len(full_text)),
                ))
            if spans:
                spans[-1] = PageSpan(page_number=len(spans), char_start=spans[-1].char_start, char_end=len(full_text))
            doc = DocumentText(text=full_text, page_count=page_count or 1, spans=spans)
            print(f"  Using existing text: {len(full_text):,} chars, {page_count} pages")
        else:
            # No full_text stored -- re-extract from PDF
            pdf_path = Path(file_path) if file_path else None
            if not pdf_path or not pdf_path.exists():
                print(f"ERROR: No full_text and PDF not found at: {file_path}")
                sys.exit(1)
            print(f"  No stored text -- re-extracting from PDF: {pdf_path.name}")
            _s1 = importlib.import_module("scripts.cba.01_extract_text")
            doc, ext_method = _s1.load_pdf_text_with_ocr(pdf_path)
            print(f"  Extracted: {len(doc.text):,} chars, {doc.page_count} pages, method={ext_method}")
            # Store the extracted text and update metadata
            file_hash = _s1.compute_file_hash(pdf_path)
            with _gc() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE cba_documents SET full_text = %s, page_count = %s, file_hash = %s, extraction_method = %s, updated_at = NOW() WHERE cba_id = %s",
                        [doc.text, doc.page_count, file_hash, ext_method, cba_id],
                    )
                    conn.commit()

        # Override args for downstream
        args.employer = emp_name or args.employer
        args.union = union_name_raw or args.union

        # Step 2: Extract parties
        print("\n" + "=" * 60)
        print("STEP 2: Extracting party/date metadata")
        print("=" * 60)
        _s2 = importlib.import_module("scripts.cba.02_extract_parties")
        meta = _s2.extract_parties_from_text(doc.text)
        print(f"  Employer:   {meta.employer_name or '(not found)'}")
        print(f"  Union:      {meta.union_name or '(not found)'}")
        _s2.update_document_metadata(cba_id, meta)

        # Entity linking
        employer_id, f_num = _s2.link_entities(cba_id, args.employer, args.union)
        print(f"  Linked employer_id: {employer_id or '(no match)'}")
        print(f"  Linked f_num:       {f_num or '(no match)'}")

        # Step 3: Find articles
        print("\n" + "=" * 60)
        print("STEP 3: Finding article/section structure")
        print("=" * 60)
        _s3 = importlib.import_module("scripts.cba.03_find_articles")
        chunks = _s3.find_articles(doc.text, doc.spans)
        print(f"  Found {len(chunks)} headings")
        _s3.save_structure(cba_id, chunks)

        # Step 4: Tag provisions
        print("\n" + "=" * 60)
        print("STEP 4: Tagging provisions with rule engine")
        print("=" * 60)
        from scripts.cba.rule_engine import match_text_all_categories, populate_context
        _s4 = importlib.import_module("scripts.cba.04_tag_category")
        from collections import Counter

        categories = args.categories.split(",") if args.categories else None
        matches = match_text_all_categories(chunks, categories, min_confidence=args.min_confidence)
        populate_context(matches, doc.text)
        print(f"  Found {len(matches)} provisions")

        cat_counts = Counter(m.category for m in matches)
        print("\n  By category:")
        for cat, cnt in cat_counts.most_common():
            print(f"    {cat}: {cnt}")

        if not args.dry_run:
            inserted = _s4.insert_provisions(cba_id, matches, doc.spans)
            with _gc() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE cba_documents SET extraction_status = 'completed', updated_at = NOW() WHERE cba_id = %s",
                        [cba_id],
                    )
                    conn.commit()
            print(f"\n  Inserted {inserted} provisions")
        else:
            print("\n  --- DRY RUN: no provisions inserted ---")

        print("\n" + "=" * 60)
        print("REPROCESS COMPLETE")
        print(f"  cba_id={cba_id}, provisions={len(matches)}, categories={len(cat_counts)}")
        print("=" * 60)
        return

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found: {pdf_path}")
        sys.exit(1)

    # --- Step 1: Extract Text ---
    print("=" * 60)
    print("STEP 1: Extracting text from PDF")
    print("=" * 60)

    _s1 = importlib.import_module("scripts.cba.01_extract_text")
    load_pdf_text, is_scanned_document, insert_document, parse_date = (
        _s1.load_pdf_text, _s1.is_scanned_document, _s1.insert_document, _s1.parse_date
    )

    doc = load_pdf_text(pdf_path)
    if is_scanned_document(doc):
        print(f"  WARNING: Document appears scanned ({len(doc.text.strip())} chars, {doc.page_count} pages)")
        print("  Continuing anyway, but extraction quality may be poor.")

    print(f"  Pages: {doc.page_count}")
    print(f"  Characters: {len(doc.text):,}")

    cba_id = insert_document(
        employer_name=args.employer,
        union_name=args.union,
        doc=doc,
        file_path=str(pdf_path),
        source_name=args.source,
        effective_date=parse_date(args.effective_date),
        expiration_date=parse_date(args.expiration_date),
    )
    print(f"  Inserted as cba_id = {cba_id}")

    # --- Step 2: Extract Parties ---
    print("\n" + "=" * 60)
    print("STEP 2: Extracting party/date metadata")
    print("=" * 60)

    _s2 = importlib.import_module("scripts.cba.02_extract_parties")
    extract_parties_from_text, update_document_metadata, link_entities = (
        _s2.extract_parties_from_text, _s2.update_document_metadata, _s2.link_entities
    )

    meta = extract_parties_from_text(doc.text)
    print(f"  Employer:   {meta.employer_name or '(not found)'}")
    print(f"  Union:      {meta.union_name or '(not found)'}")
    print(f"  Local:      {meta.local_number or '(not found)'}")
    print(f"  Effective:  {meta.effective_date or '(not found)'}")
    print(f"  Expiration: {meta.expiration_date or '(not found)'}")
    print(f"  State:      {meta.state or '(not found)'}")
    print(f"  City:       {meta.city or '(not found)'}")
    update_document_metadata(cba_id, meta)

    # Entity linking
    employer_id, f_num = link_entities(cba_id, args.employer, args.union)
    print(f"  Linked employer_id: {employer_id or '(no match)'}")
    print(f"  Linked f_num:       {f_num or '(no match)'}")

    # --- Step 3: Find Articles ---
    print("\n" + "=" * 60)
    print("STEP 3: Finding article/section structure")
    print("=" * 60)

    _s3 = importlib.import_module("scripts.cba.03_find_articles")
    find_articles, save_structure = _s3.find_articles, _s3.save_structure

    spans = doc.spans  # Use exact spans from PDF extraction
    chunks = find_articles(doc.text, spans)
    print(f"  Found {len(chunks)} headings")

    if args.verbose and chunks:
        print("\n  Outline:")
        for c in chunks:
            indent = "  " * c.level
            page_info = f"p.{c.page_start}" if c.page_start else ""
            print(f"    {indent}{c.number}. {c.title} {page_info}")

    save_structure(cba_id, chunks)

    if not chunks:
        print("  WARNING: No article structure found. Rule engine may produce fewer results.")

    # --- Step 4: Tag Provisions ---
    print("\n" + "=" * 60)
    print("STEP 4: Tagging provisions with rule engine")
    print("=" * 60)

    from scripts.cba.rule_engine import match_text_all_categories, populate_context
    _s4 = importlib.import_module("scripts.cba.04_tag_category")
    insert_provisions = _s4.insert_provisions
    from collections import Counter

    categories = args.categories.split(",") if args.categories else None
    matches = match_text_all_categories(chunks, categories, min_confidence=args.min_confidence)
    populate_context(matches, doc.text)
    print(f"  Found {len(matches)} provisions")

    # Summary
    cat_counts = Counter(m.category for m in matches)
    class_counts = Counter(m.provision_class for m in matches)

    print("\n  By category:")
    for cat, cnt in cat_counts.most_common():
        print(f"    {cat}: {cnt}")

    print("\n  By provision class:")
    for cls, cnt in class_counts.most_common(10):
        print(f"    {cls}: {cnt}")
    if len(class_counts) > 10:
        print(f"    ... and {len(class_counts) - 10} more classes")

    if args.dry_run:
        print("\n  --- DRY RUN: no provisions inserted ---")
        if args.verbose:
            for m in matches[:10]:
                snippet = m.matched_text[:80].replace("\n", " ")
                print(f"    [{m.confidence:.2f}] {m.category}/{m.provision_class} ({m.rule_name})")
                print(f"           {snippet}...")
            if len(matches) > 10:
                print(f"    ... and {len(matches) - 10} more")
    else:
        inserted = insert_provisions(cba_id, matches, spans)
        from db_config import get_connection
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cba_documents SET extraction_status = 'completed', updated_at = NOW() WHERE cba_id = %s",
                    [cba_id],
                )
                conn.commit()
        print(f"\n  Inserted {inserted} provisions")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE")
    print("=" * 60)
    print(f"  cba_id:       {cba_id}")
    print(f"  Pages:        {doc.page_count}")
    print(f"  Articles:     {len(chunks)}")
    print(f"  Provisions:   {len(matches)}")
    print(f"  Categories:   {len(cat_counts)}")
    print(f"  Dry run:      {args.dry_run}")
    if not args.dry_run:
        print(f"\n  Next steps:")
        print(f"    Review: py scripts/cba/review_provisions.py --cba-id {cba_id}")
        print(f"    API:    GET /api/cba/documents/{cba_id}")


if __name__ == "__main__":
    main()
