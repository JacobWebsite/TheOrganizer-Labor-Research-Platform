"""Interactive review CLI for rule-engine-extracted provisions.

Shows each provision with context, confidence, and rule name.
User can approve, delete, recategorize, skip, or add notes.
Every correction is logged to cba_reviews.

Usage:
    py scripts/cba/review_provisions.py --cba-id N [--category healthcare] [--min-confidence 0.50]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection

# Valid categories for recategorization
VALID_CATEGORIES = [
    "healthcare", "wages", "grievance", "leave", "pension",
    "seniority", "management_rights", "union_security", "scheduling",
    "job_security", "childcare", "training", "technology", "other",
]


def fetch_provisions(cba_id: int, category: str | None = None, min_confidence: float = 0.0):
    """Fetch provisions for review."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            sql = """
                SELECT provision_id, category, provision_class, provision_text,
                       confidence_score, rule_name, article_reference,
                       modal_verb, legal_weight, is_human_verified
                FROM cba_provisions
                WHERE cba_id = %s AND extraction_method = 'rule_engine'
            """
            params = [cba_id]
            if category:
                sql += " AND category = %s"
                params.append(category)
            if min_confidence > 0:
                sql += " AND confidence_score >= %s"
                params.append(min_confidence)
            sql += " ORDER BY page_start NULLS LAST, provision_id"

            cur.execute(sql, params)
            columns = [desc[0] for desc in cur.description]
            return [dict(zip(columns, row)) for row in cur.fetchall()]


def log_review(provision_id: int, original_category: str, corrected_category: str | None,
               original_class: str, corrected_class: str | None,
               reviewer: str, action: str, notes: str | None = None):
    """Log a review action to cba_reviews."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO cba_reviews (
                    provision_id, original_category, corrected_category,
                    original_class, corrected_class,
                    reviewer, review_action, notes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [provision_id, original_category, corrected_category,
                 original_class, corrected_class,
                 reviewer, action, notes],
            )
            conn.commit()


def approve_provision(provision_id: int):
    """Mark a provision as human-verified."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE cba_provisions SET is_human_verified = TRUE WHERE provision_id = %s",
                [provision_id],
            )
            conn.commit()


def delete_provision(provision_id: int):
    """Delete a provision."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM cba_provisions WHERE provision_id = %s", [provision_id])
            conn.commit()


def recategorize_provision(provision_id: int, new_category: str, new_class: str | None = None):
    """Change a provision's category (and optionally class)."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            if new_class:
                cur.execute(
                    "UPDATE cba_provisions SET category = %s, provision_class = %s, is_human_verified = TRUE WHERE provision_id = %s",
                    [new_category, new_class, provision_id],
                )
            else:
                cur.execute(
                    "UPDATE cba_provisions SET category = %s, is_human_verified = TRUE WHERE provision_id = %s",
                    [new_category, provision_id],
                )
            conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Interactive review of CBA provisions")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to review")
    parser.add_argument("--category", default=None, help="Filter to a single category")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="Minimum confidence to show")
    parser.add_argument("--reviewer", default="admin", help="Reviewer name for audit trail")
    args = parser.parse_args()

    provisions = fetch_provisions(args.cba_id, args.category, args.min_confidence)
    if not provisions:
        print(f"No provisions found for cba_id={args.cba_id}")
        return

    print(f"\nReviewing {len(provisions)} provisions for cba_id={args.cba_id}")
    print("Commands: [Enter]=approve, d=delete, c <cat>=recategorize, s=skip, n <note>=add note, q=quit\n")

    reviewed = 0
    approved = 0
    deleted = 0
    recategorized = 0

    for i, prov in enumerate(provisions, 1):
        pid = prov["provision_id"]
        cat = prov["category"]
        cls = prov["provision_class"]
        conf = float(prov["confidence_score"]) if prov["confidence_score"] else 0
        rule = prov["rule_name"] or "?"
        modal = prov["modal_verb"] or "-"
        verified = "V" if prov["is_human_verified"] else " "
        text = (prov["provision_text"] or "")[:300].replace("\n", " ")
        art_ref = prov["article_reference"] or ""

        print(f"--- [{i}/{len(provisions)}] provision_id={pid} [{verified}] ---")
        print(f"  Category: {cat} / {cls}")
        print(f"  Confidence: {conf:.2f}  Rule: {rule}  Modal: {modal}")
        if art_ref:
            print(f"  Article: {art_ref}")
        print(f"  Text: {text}")
        print()

        try:
            action = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            break

        if action == "q":
            break
        elif action == "" or action == "a":
            approve_provision(pid)
            log_review(pid, cat, None, cls, None, args.reviewer, "approve")
            approved += 1
        elif action == "d":
            delete_provision(pid)
            log_review(pid, cat, None, cls, None, args.reviewer, "delete")
            deleted += 1
        elif action.startswith("c "):
            new_cat = action[2:].strip()
            if new_cat not in VALID_CATEGORIES:
                print(f"  Invalid category. Valid: {', '.join(VALID_CATEGORIES)}")
                continue
            recategorize_provision(pid, new_cat)
            log_review(pid, cat, new_cat, cls, None, args.reviewer, "recategorize")
            recategorized += 1
        elif action.startswith("n "):
            note = action[2:].strip()
            log_review(pid, cat, None, cls, None, args.reviewer, "approve", notes=note)
            approve_provision(pid)
            approved += 1
        elif action == "s":
            pass  # skip
        else:
            print("  Unknown command. Skipping.")

        reviewed += 1

    print(f"\nReview complete: {reviewed} reviewed, {approved} approved, {deleted} deleted, {recategorized} recategorized")


if __name__ == "__main__":
    main()
