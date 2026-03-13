"""Script 4: Tag provisions by category using the rule engine.

Runs rule-based matching against the article chunks for a document,
then inserts matching provisions into cba_provisions.

Usage:
    py scripts/cba/04_tag_category.py --cba-id N --category healthcare --dry-run
    py scripts/cba/04_tag_category.py --cba-id N --category healthcare
    py scripts/cba/04_tag_category.py --cba-id N --all
    py scripts/cba/04_tag_category.py --cba-id N --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import ArticleChunk, PageSpan
import importlib

from scripts.cba.rule_engine import (
    filter_toc_index_chunks,
    load_all_rules,
    load_category_rules,
    match_all_chunks,
    match_text_all_categories,
    populate_context,
)

_article_mod = importlib.import_module("scripts.cba.03_find_articles")
_page_for_char = _article_mod._page_for_char


def get_chunks_and_spans(cba_id: int) -> tuple[list[ArticleChunk], list[PageSpan], str]:
    """Load article chunks and spans for a document."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT full_text, structure_json, page_count FROM cba_documents WHERE cba_id = %s",
                [cba_id],
            )
            row = cur.fetchone()
            if not row or not row[0]:
                return [], [], ""

            text, structure_json, page_count = row

            # Reconstruct spans
            page_count = page_count or 1
            chars_per_page = len(text) // max(page_count, 1)
            spans = []
            for i in range(page_count):
                spans.append(PageSpan(
                    page_number=i + 1,
                    char_start=i * chars_per_page,
                    char_end=min((i + 1) * chars_per_page, len(text)),
                ))
            if spans:
                spans[-1] = PageSpan(
                    page_number=page_count,
                    char_start=spans[-1].char_start,
                    char_end=len(text),
                )

            # Reconstruct chunks from structure_json
            chunks = []
            if structure_json:
                for item in structure_json:
                    cs = item["char_start"]
                    ce = item["char_end"]
                    chunks.append(ArticleChunk(
                        number=item["number"],
                        title=item.get("title", ""),
                        level=item.get("level", 1),
                        text=text[cs:ce],
                        char_start=cs,
                        char_end=ce,
                        page_start=item.get("page_start"),
                        page_end=item.get("page_end"),
                        parent_number=item.get("parent_number"),
                    ))

            return chunks, spans, text


def insert_provisions(cba_id: int, matches, spans: list[PageSpan]) -> int:
    """Insert rule-engine matches as provisions."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            inserted = 0
            for m in matches:
                page_start = _page_for_char(spans, m.char_start)
                page_end = _page_for_char(spans, max(m.char_end - 1, m.char_start))

                cur.execute(
                    """
                    INSERT INTO cba_provisions (
                        cba_id, category, provision_class, provision_text,
                        summary, page_start, page_end, char_start, char_end,
                        modal_verb, legal_weight, confidence_score,
                        model_version, is_human_verified,
                        extraction_method, rule_name, article_reference,
                        context_before, context_after
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            'rule_engine', FALSE, 'rule_engine', %s, %s, %s, %s)
                    """,
                    [
                        cba_id, m.category, m.provision_class, m.matched_text,
                        m.summary, page_start, page_end, m.char_start, m.char_end,
                        m.modal_verb, m.legal_weight, m.confidence,
                        m.rule_name, m.article_reference,
                        getattr(m, 'context_before', None),
                        getattr(m, 'context_after', None),
                    ],
                )
                inserted += 1
            conn.commit()
    return inserted


def main() -> None:
    parser = argparse.ArgumentParser(description="Tag CBA provisions by category")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--category", help="Single category to run")
    group.add_argument("--all", action="store_true", help="Run all categories")
    parser.add_argument("--categories", help="Comma-separated list of categories")
    parser.add_argument("--dry-run", action="store_true", help="Print matches without inserting")
    parser.add_argument("--min-confidence", type=float, default=0.50, help="Minimum confidence threshold")
    args = parser.parse_args()

    chunks, spans, text = get_chunks_and_spans(args.cba_id)
    if not chunks:
        print(f"ERROR: No article structure found for cba_id={args.cba_id}")
        print("  Run 03_find_articles.py first.")
        sys.exit(1)

    print(f"Processing cba_id={args.cba_id}: {len(chunks)} chunks")

    # Get page count for TOC/Index filter
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT page_count FROM cba_documents WHERE cba_id = %s", [args.cba_id])
            row = cur.fetchone()
            total_pages = row[0] if row else None

    if args.all or args.categories:
        categories = args.categories.split(",") if args.categories else None
        matches = match_text_all_categories(
            chunks, categories, min_confidence=args.min_confidence,
            total_pages=total_pages,
        )
    else:
        rules = load_category_rules(args.category)
        if not rules:
            print(f"ERROR: No rules found for category '{args.category}'")
            print(f"  Expected: config/cba_rules/{args.category}.json")
            sys.exit(1)
        # Apply TOC/Index filter for single-category runs too
        working_chunks = filter_toc_index_chunks(chunks, total_pages)
        matches = match_all_chunks(working_chunks, rules, min_confidence=args.min_confidence)

    # Populate context windows from full document text
    populate_context(matches, text)

    print(f"  Found {len(matches)} provisions")

    # Summary by category/class
    from collections import Counter
    class_counts = Counter(m.provision_class for m in matches)
    cat_counts = Counter(m.category for m in matches)

    print("\n  By category:")
    for cat, cnt in cat_counts.most_common():
        print(f"    {cat}: {cnt}")

    print("\n  By provision class:")
    for cls, cnt in class_counts.most_common():
        print(f"    {cls}: {cnt}")

    if args.dry_run:
        print("\n  --- DRY RUN: sample matches ---")
        for m in matches[:20]:
            conf = f"{m.confidence:.2f}"
            modal = m.modal_verb or "-"
            snippet = m.matched_text[:100].replace("\n", " ")
            print(f"    [{conf}] {m.category}/{m.provision_class} ({m.rule_name}) [{modal}]")
            print(f"           {snippet}...")
            if m.article_reference:
                print(f"           @ {m.article_reference}")
            print()
        if len(matches) > 20:
            print(f"    ... and {len(matches) - 20} more")
        print("\n  No data inserted (dry run).")
    else:
        inserted = insert_provisions(args.cba_id, matches, spans)
        # Update document status
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cba_documents SET extraction_status = 'completed', updated_at = NOW() WHERE cba_id = %s",
                    [args.cba_id],
                )
                conn.commit()
        print(f"\n  Inserted {inserted} provisions into cba_provisions.")


if __name__ == "__main__":
    main()
