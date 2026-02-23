"""
Phase 1.5: Flag junk/placeholder records in f7_employers_deduped.

This script flags records for exclusion from scoring. It does NOT delete rows.

Default mode is dry-run.
Use --commit to persist updates.
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


PLACEHOLDER_EXACT = {
    "company lists",
    "company list",
    "employer name",
    "m1",
    "n/a",
    "na",
    "none",
    "unknown",
    "test",
    "tbd",
    "see attached spreadsheets for employer names",
}

KNOWN_NON_EMPLOYERS = {
    "pension benefit guaranty corporation",
    "pension benefit guaranty corporation (pbgc)",
    "laner muchin",
    "csp-c/o laner muchin",
}

# Conservative federal/public-sector agency pattern (not all public employers).
AGENCY_PATTERN = re.compile(
    r"(?i)"
    r"(?:"
    r"\bpension benefit guaranty\b"
    r"|^internal revenue service\b"
    r"|^social security administration\b"
    r"|^u\.?s\.?\s+postal service\b"
    r"|^usps\b"
    r"|^department of veterans affairs\b"
    r"|^bureau of\b"
    r")"
)


def normalize_name(name: str) -> str:
    return (name or "").strip().lower()


def alnum_len(name: str) -> int:
    return len(re.sub(r"[^A-Za-z0-9]", "", name or ""))


def classify_record(name: str, state: str, is_labor_org: bool):
    reasons = []
    n = normalize_name(name)
    l = alnum_len(name)

    if n in PLACEHOLDER_EXACT:
        reasons.append("PLACEHOLDER_NAME")

    # Empty/symbol-only strings and very short names are almost always junk placeholders.
    if l == 0:
        reasons.append("NO_ALNUM_NAME")
    elif l <= 2:
        reasons.append("NAME_TOO_SHORT")

    if n in KNOWN_NON_EMPLOYERS:
        reasons.append("KNOWN_NON_EMPLOYER")

    if AGENCY_PATTERN.search(name or ""):
        reasons.append("GOVERNMENT_AGENCY")

    # Known aggregation artifact from roadmap.
    if ("usps" in n or "postal service" in n) and (state or "").upper() == "TX":
        reasons.append("AGGREGATION_ARTIFACT_USPS_TX")

    # Keep this separate for downstream review.
    if bool(is_labor_org):
        reasons.append("IS_LABOR_ORG_REVIEW")

    return reasons


def ensure_columns(cur):
    cur.execute(
        """
        ALTER TABLE f7_employers_deduped
        ADD COLUMN IF NOT EXISTS exclude_from_scoring BOOLEAN DEFAULT FALSE
        """
    )


def main():
    parser = argparse.ArgumentParser(description="Flag junk records in f7_employers_deduped")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    parser.add_argument(
        "--include-labor-org-review",
        action="store_true",
        help="Also flag records where is_labor_org=TRUE",
    )
    parser.add_argument("--limit-preview", type=int, default=30, help="Rows to preview")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()

    try:
        ensure_columns(cur)

        cur.execute(
            """
            SELECT employer_id, employer_name, state, is_labor_org,
                   COALESCE(exclude_reason, ''), COALESCE(exclude_from_scoring, FALSE)
            FROM f7_employers_deduped
            """
        )
        rows = cur.fetchall()

        flagged = []
        for employer_id, employer_name, state, is_labor_org, existing_reason, existing_flag in rows:
            reasons = classify_record(employer_name, state, is_labor_org)
            if not args.include_labor_org_review:
                reasons = [r for r in reasons if r != "IS_LABOR_ORG_REVIEW"]
            if not reasons:
                continue
            reason_str = ";".join(sorted(set(reasons)))
            merged_reason = ";".join(
                [p for p in [existing_reason.strip("; "), reason_str] if p]
            )
            flagged.append((employer_id, merged_reason, existing_flag))

        print(f"Total records scanned: {len(rows):,}")
        print(f"Records matched junk rules: {len(flagged):,}")

        if flagged:
            print("\nPreview:")
            cur.execute(
                """
                SELECT employer_id, employer_name, state, is_labor_org
                FROM f7_employers_deduped
                WHERE employer_id = ANY(%s)
                ORDER BY employer_name
                LIMIT %s
                """,
                ([f[0] for f in flagged], args.limit_preview),
            )
            for r in cur.fetchall():
                print(r)

        updates = 0
        for employer_id, merged_reason, _existing_flag in flagged:
            cur.execute(
                """
                UPDATE f7_employers_deduped
                SET exclude_from_scoring = TRUE,
                    exclude_reason = %s
                WHERE employer_id = %s
                """,
                (merged_reason, employer_id),
            )
            updates += cur.rowcount

        print(f"\nRows updated: {updates:,}")

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

