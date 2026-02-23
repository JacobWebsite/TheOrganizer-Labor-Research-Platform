"""Infer missing NAICS from employer-name keyword patterns.

Rules:
- only rows where f7_employers_deduped.naics IS NULL
- map keywords to specific 6-digit NAICS codes (examples: hospital -> 622110)
- update only when exactly one NAICS code is inferred
- set naics_source='KEYWORD_INFERRED'
- dry-run by default, --commit to persist
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


CATEGORY_RULES = {
    "construction": {"naics": "236220", "patterns": [r"\bconstruction\b", r"\bbuilder[s]?\b", r"\bcontractor[s]?\b", r"\bplumbing\b", r"\belectric(al)?\b", r"\broofing\b", r"\bhvac\b", r"\bmasonry\b"]},
    "healthcare": {"naics": "622110", "patterns": [r"\bhospital\b", r"\bmedical\b", r"\bhealth\b", r"\bclinic\b", r"\bnursing\b", r"\brehab"]},
    "education": {"naics": "611110", "patterns": [r"\bschool\b", r"\buniversity\b", r"\bcollege\b", r"\beducation\b", r"\bacademy\b"]},
    "hospitality_food": {"naics": "722511", "patterns": [r"\bhotel\b", r"\bmotel\b", r"\bresort\b", r"\brestaurant\b", r"\bfood service\b", r"\bcafe\b", r"\bbakery\b"]},
    "transportation": {"naics": "484110", "patterns": [r"\btrucking\b", r"\bfreight\b", r"\btransport\b", r"\blogistics\b", r"\bmoving\b", r"\bshipping\b"]},
    "manufacturing": {"naics": "339999", "patterns": [r"\bmanufacturing\b", r"\bfabricat", r"\bmachine shop\b", r"\bfoundry\b", r"\bassembly\b"]},
    "retail": {"naics": "452319", "patterns": [r"\bgrocery\b", r"\bsupermarket\b", r"\bretail\b", r"\bstore\b", r"\bshop\b", r"\bmart\b"]},
    "finance": {"naics": "522110", "patterns": [r"\bbank\b", r"\bcredit union\b", r"\binsurance\b", r"\bfinancial\b"]},
    "mining": {"naics": "211120", "patterns": [r"\bmining\b", r"\bquarry\b", r"\boil\b", r"\bgas\b", r"\bdrilling\b"]},
    "agriculture": {"naics": "111998", "patterns": [r"\bfarm\b", r"\branch\b", r"\bagriculture\b", r"\bdairy\b", r"\blivestock\b"]},
    "warehousing": {"naics": "493110", "patterns": [r"\bwarehouse\b", r"\bdistribution center\b", r"\bfulfillment\b"]},
    "admin_support": {"naics": "561720", "patterns": [r"\bcleaning\b", r"\bjanitorial\b", r"\bcustodial\b", r"\blaundry\b"]},
}

COMPILED_RULES = []
for category, cfg in CATEGORY_RULES.items():
    for pattern in cfg["patterns"]:
        COMPILED_RULES.append((category, re.compile(pattern, re.IGNORECASE)))


def infer_categories(name: str):
    text = (name or "").strip()
    if not text:
        return []
    hits = []
    for category, pattern in COMPILED_RULES:
        if pattern.search(text):
            hits.append((category, pattern.pattern))
    return hits


def main():
    parser = argparse.ArgumentParser(description="Infer NAICS from employer-name keywords")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode (default if --commit omitted)")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT employer_id, employer_name
            FROM f7_employers_deduped
            WHERE naics IS NULL
            """
        )
        rows = cur.fetchall()

        updates = []
        ambiguous = 0
        no_match = 0
        by_code = Counter()
        by_pattern = Counter()
        by_category = Counter()
        conflict_examples = []
        for employer_id, employer_name in rows:
            hits = infer_categories(employer_name)
            categories = sorted({category for category, _pattern in hits})
            codes = sorted({CATEGORY_RULES[c]["naics"] for c in categories})
            if len(codes) == 1:
                naics_code = codes[0]
                updates.append((naics_code, employer_id))
                by_code[naics_code] += 1
                for category in categories:
                    by_category[category] += 1
                for _category, pattern_text in hits:
                    by_pattern[pattern_text] += 1
            elif len(codes) > 1:
                ambiguous += 1
                if len(conflict_examples) < 20:
                    conflict_examples.append((employer_name, categories))
            else:
                no_match += 1

        print(f"NULL NAICS rows scanned: {len(rows):,}")
        print(f"Unique-code keyword matches: {len(updates):,}")
        print(f"Ambiguous multi-sector matches: {ambiguous:,}")
        print(f"No keyword match: {no_match:,}")
        print("\nMatches by 6-digit NAICS code:")
        for naics, cnt in sorted(by_code.items(), key=lambda x: x[1], reverse=True):
            print(f"  {naics}: {cnt:,}")
        print("\nMatches by category:")
        for category, cnt in sorted(by_category.items(), key=lambda x: x[1], reverse=True):
            print(f"  {category}: {cnt:,}")
        print("\nPattern hit counts (for rows that were uniquely inferred):")
        for label, cnt in sorted(by_pattern.items(), key=lambda x: x[1], reverse=True):
            print(f"  {label}: {cnt:,}")
        if conflict_examples:
            print("\nSample ambiguous rows:")
            for name, category_list in conflict_examples:
                print(f"  {name} -> {', '.join(category_list)}")

        updated = 0
        for naics_code, employer_id in updates:
            cur.execute(
                """
                UPDATE f7_employers_deduped
                SET naics = %s,
                    naics_source = 'KEYWORD_INFERRED'
                WHERE employer_id = %s
                  AND naics IS NULL
                """,
                (naics_code, employer_id),
            )
            updated += cur.rowcount

        print(f"\nRows updated in transaction: {updated:,}")

        cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE naics IS NULL")
        remaining_null = cur.fetchone()[0]
        print(f"Remaining NULL NAICS (post-transaction view): {remaining_null:,}")

        if args.commit:
            conn.commit()
            print("Committed.")
        else:
            conn.rollback()
            print("Dry-run complete (rolled back). Use --commit to persist.")
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
