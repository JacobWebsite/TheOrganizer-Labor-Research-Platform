"""Script 8: Enrich sections with structured attributes (Pass 3).

Populates cba_sections.attributes JSONB with:
  - word_count: integer
  - categories_detected: list of category names from rule engine
  - has_wage_table: boolean
  - linked_provision_ids: list of existing cba_provisions IDs in this section
  - key_terms: significant terms from heading signals

Usage:
    py scripts/cba/08_enrich_sections.py --cba-id 26 [--verbose]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import ArticleChunk
from scripts.cba.rule_engine import (
    load_all_rules,
    match_chunk,
    score_heading,
)

# Wage table detection pattern
WAGE_TABLE_RE = re.compile(r"\$\s*\d+[.,]\d{2}")


def enrich_sections(cba_id: int, verbose: bool = False) -> int:
    """Compute and store attributes for all sections of a document."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            # Load all sections
            cur.execute(
                """
                SELECT section_id, section_num, section_title, section_level,
                       section_text, char_start, char_end
                FROM cba_sections
                WHERE cba_id = %s
                ORDER BY sort_order
                """,
                [cba_id],
            )
            sections = cur.fetchall()

            if not sections:
                print(f"  No sections found for cba_id={cba_id}")
                return 0

            # Load all provisions for this document (for linking)
            cur.execute(
                """
                SELECT provision_id, char_start, char_end
                FROM cba_provisions
                WHERE cba_id = %s
                """,
                [cba_id],
            )
            provisions = cur.fetchall()

    # Load rule engine rules
    all_rules = load_all_rules()

    enriched = 0
    for section_id, sec_num, sec_title, sec_level, sec_text, sec_cs, sec_ce in sections:
        attrs = {}

        # 1. Word count
        words = len(sec_text.split())
        attrs["word_count"] = words

        # 2. Categories detected -- run rule engine on this section as a chunk
        chunk = ArticleChunk(
            number=sec_num,
            title=sec_title,
            level=sec_level,
            text=sec_text,
            char_start=sec_cs,
            char_end=sec_ce,
        )
        categories = set()
        for rules in all_rules:
            matches = match_chunk(chunk, rules, min_confidence=0.50)
            if matches:
                categories.add(rules.category)
        attrs["categories_detected"] = sorted(categories)

        # 3. Has wage table
        wage_matches = WAGE_TABLE_RE.findall(sec_text)
        attrs["has_wage_table"] = len(wage_matches) >= 3

        # 4. Linked provision IDs
        linked = []
        for prov_id, prov_cs, prov_ce in provisions:
            if prov_cs is not None and prov_ce is not None:
                # Provision falls within this section if there's substantial overlap
                overlap_start = max(sec_cs, prov_cs)
                overlap_end = min(sec_ce, prov_ce)
                if overlap_end > overlap_start:
                    linked.append(prov_id)
        attrs["linked_provision_ids"] = linked

        # 5. Key terms from heading signals
        key_terms = []
        for rules in all_rules:
            hs = score_heading(sec_title, rules)
            if hs >= 0.3:
                key_terms.append(rules.category)
        attrs["key_terms"] = key_terms

        # Update the section
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE cba_sections SET attributes = %s, updated_at = NOW() WHERE section_id = %s",
                    [json.dumps(attrs), section_id],
                )
                conn.commit()

        enriched += 1
        if verbose:
            cats = ", ".join(attrs["categories_detected"]) or "(none)"
            linked_count = len(attrs["linked_provision_ids"])
            print(f"  {sec_num}. {sec_title}: {words} words, "
                  f"cats=[{cats}], provisions={linked_count}, "
                  f"wage_table={attrs['has_wage_table']}")

    return enriched


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich CBA sections with attributes")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    parser.add_argument("--verbose", action="store_true", help="Print detailed output")
    args = parser.parse_args()

    # Verify sections exist
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM cba_sections WHERE cba_id = %s",
                [args.cba_id],
            )
            count = cur.fetchone()[0]

    if count == 0:
        print(f"ERROR: No sections found for cba_id={args.cba_id}")
        print("  Run 06_split_sections.py first.")
        sys.exit(1)

    print(f"Enriching {count} sections for cba_id={args.cba_id}")

    enriched = enrich_sections(args.cba_id, verbose=args.verbose)
    print(f"  Enriched {enriched} sections with attributes")

    # Update decomposition status
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cba_documents SET decomposition_status = 'enriched', updated_at = NOW() WHERE cba_id = %s",
                [args.cba_id],
            )
            conn.commit()

    # Summary stats
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) AS total,
                    COUNT(*) FILTER (WHERE attributes->>'has_wage_table' = 'true') AS wage_tables,
                    COUNT(*) FILTER (WHERE jsonb_array_length(attributes->'categories_detected') > 0) AS with_categories,
                    COUNT(*) FILTER (WHERE jsonb_array_length(attributes->'linked_provision_ids') > 0) AS with_provisions
                FROM cba_sections
                WHERE cba_id = %s
                """,
                [args.cba_id],
            )
            row = cur.fetchone()
            total, wage, cats, provs = row
            print(f"\n  Summary:")
            print(f"    Total sections:       {total}")
            print(f"    With wage tables:     {wage}")
            print(f"    With categories:      {cats}")
            print(f"    With provisions:      {provs}")


if __name__ == "__main__":
    main()
