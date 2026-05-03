"""Extract high-confidence sub-fields from CBA articles.

Combines article CATEGORY (from title matching) with targeted REGEX patterns
to extract structured data with 90%+ confidence. Category gating is what
makes this reliable: "$22.50 per hour" in a wages article = base rate.

Tier 1 (95%+): contract_term_years, holiday_count, holiday_pay_rate,
    overtime_rate_multiplier, grievance_step_count, has_no_strike_clause,
    probationary_period

Usage:
    py scripts/cba/extract_article_subfields.py --all
    py scripts/cba/extract_article_subfields.py --cba-id 26
    py scripts/cba/extract_article_subfields.py --audit
    py scripts/cba/extract_article_subfields.py --all --dry-run
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection


# ── Tier 1 Extractors (95%+ confidence) ────────────────────────────
#
# Each returns {"field_name": {value, display, raw_match, confidence}}
# or None if no confident match found.


_MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
}

_DATE_RE = re.compile(
    r'(January|February|March|April|May|June|July|August|September|October|November|December)'
    r'\s+(\d{1,2}),?\s+(\d{4})',
    re.IGNORECASE,
)


def extract_contract_term_years(text: str) -> dict | None:
    """Extract contract duration in years from duration articles."""
    # Method 1: explicit "X-year agreement"
    m = re.search(
        r'(\d+)\s*[-]?\s*year\s+(agreement|contract|term|period|duration)',
        text, re.IGNORECASE,
    )
    if m:
        years = int(m.group(1))
        if 1 <= years <= 10:
            return {"contract_term_years": {
                "value": years,
                "display": f"{years}-year agreement",
                "raw_match": m.group(0).strip(),
                "confidence": 0.97,
            }}

    # Method 2: compute from effective/expiration dates
    # Find dates near "effective/commence" and "expire/terminate/ending/through"
    dates = list(_DATE_RE.finditer(text))
    if len(dates) < 2:
        return None

    eff_date = None
    exp_date = None

    for dm in dates:
        month = _MONTH_MAP.get(dm.group(1).lower())
        day = int(dm.group(2))
        year = int(dm.group(3))
        if not (2000 <= year <= 2035):
            continue

        # Check context: 100 chars before the date
        context_start = max(0, dm.start() - 100)
        context = text[context_start:dm.start()].lower()

        if re.search(r'effective|commenc|begin|start|from', context):
            if eff_date is None:
                eff_date = (year, month, day, dm.group(0).strip())
        elif re.search(r'expir|terminat|end|through|until|conclud', context):
            if exp_date is None:
                exp_date = (year, month, day, dm.group(0).strip())

    # Fallback: if we found 2+ dates but no context keywords, use first and last
    if eff_date is None or exp_date is None:
        all_dates = []
        for dm in dates:
            year = int(dm.group(3))
            month = _MONTH_MAP.get(dm.group(1).lower())
            day = int(dm.group(2))
            if 2000 <= year <= 2035:
                all_dates.append((year, month, day, dm.group(0).strip()))
        if len(all_dates) >= 2:
            all_dates.sort()
            eff_date = all_dates[0]
            exp_date = all_dates[-1]

    if eff_date and exp_date:
        year_diff = exp_date[0] - eff_date[0]
        month_diff = exp_date[1] - eff_date[1]
        total_months = year_diff * 12 + month_diff
        years = round(total_months / 12)
        if 1 <= years <= 10:
            return {"contract_term_years": {
                "value": years,
                "display": f"{years}-year agreement",
                "raw_match": f"{eff_date[3]} to {exp_date[3]}",
                "confidence": 0.93,
            }}

    return None


def extract_holiday_count(text: str) -> dict | None:
    """Count named US holidays in holiday articles."""
    holidays = [
        r"new\s+year",
        r"martin\s+luther\s+king|mlk\b|king\s+jr",
        r"president",
        r"memorial\s+day",
        r"independence\s+day|fourth\s+of\s+july|july\s+4",
        r"labor\s+day",
        r"columbus\s+day|indigenous\s+people",
        r"veteran",
        r"thanksgiving",
        r"christmas",
        r"good\s+friday",
        r"easter",
        r"juneteenth",
        r"election\s+day",
    ]
    found = set()
    for i, pattern in enumerate(holidays):
        if re.search(pattern, text, re.IGNORECASE):
            found.add(i)

    # Also check for "personal" / "floating" holidays
    floating = 0
    fm = re.search(r'(\d+)\s+(?:personal|floating)\s+holiday', text, re.IGNORECASE)
    if fm:
        floating = int(fm.group(1))

    if len(found) >= 3:
        total = len(found) + floating
        display = f"{len(found)} named holidays"
        if floating:
            display += f" + {floating} floating"
        return {"holiday_count": {
            "value": total,
            "display": display,
            "raw_match": f"{len(found)} named holidays identified in text",
            "confidence": 0.96,
        }}
    return None


def extract_holiday_pay_rate(text: str) -> dict | None:
    """Extract holiday premium pay rate."""
    patterns = [
        (r'(?:double\s+time\s+and\s+(?:a\s+|one\s+)?half|2\.5\s*x|250\s*%)', "2.5", "Double time and one-half"),
        (r'(?:double\s+time|2\s*x|200\s*%)', "2.0", "Double time"),
        (r'(?:triple\s+time|3\s*x|300\s*%)', "3.0", "Triple time"),
        (r'(?:time\s+and\s+(?:a\s+|one\s+)?half|1\.5\s*x?|150\s*%|one\s+and\s+one[\s-]half)', "1.5", "Time and one-half"),
        (r'(?:straight[\s-]?time)', "1.0", "Straight time"),
    ]
    for pattern, value, display in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return {"holiday_pay_rate": {
                "value": value,
                "display": display,
                "raw_match": m.group(0).strip(),
                "confidence": 0.96,
            }}
    return None


def extract_overtime_multiplier(text: str) -> dict | None:
    """Extract overtime rate multiplier from wages articles."""
    patterns = [
        (r'(?:double\s+time\s+and\s+(?:a\s+|one\s+)?half|2\.5\s*x)', "2.5", "Double time and one-half"),
        (r'(?:double\s+time|2\s*x)', "2.0", "Double time"),
        (r'(?:time\s+and\s+(?:a\s+|one\s+)?half|1\.5\s*x?|one\s+and\s+one[\s-]half)', "1.5", "Time and one-half"),
    ]
    # Must be near "overtime" (within 300 chars)
    ot_positions = [m.start() for m in re.finditer(r'overtime', text, re.IGNORECASE)]
    if not ot_positions:
        return None

    for pattern, value, display in patterns:
        for m in re.finditer(pattern, text, re.IGNORECASE):
            # Check proximity to any "overtime" mention
            for ot_pos in ot_positions:
                if abs(m.start() - ot_pos) < 300:
                    return {"overtime_rate_multiplier": {
                        "value": value,
                        "display": display,
                        "raw_match": m.group(0).strip(),
                        "confidence": 0.95,
                    }}
    return None


def extract_grievance_step_count(text: str) -> dict | None:
    """Count grievance steps from step numbering."""
    # Look for "Step 1", "Step 2", etc.
    steps = set()
    for m in re.finditer(r'Step\s+(\d+)', text, re.IGNORECASE):
        steps.add(int(m.group(1)))

    # Also check for "N-step" pattern
    m_n = re.search(r'(\d+)[\s-]step\s+(?:grievance|procedure|process)', text, re.IGNORECASE)
    if m_n:
        n = int(m_n.group(1))
        if 2 <= n <= 8:
            return {"grievance_step_count": {
                "value": n,
                "display": f"{n}-step process",
                "raw_match": m_n.group(0).strip(),
                "confidence": 0.97,
            }}

    if len(steps) >= 2:
        count = max(steps)
        if 2 <= count <= 8:  # sanity check
            return {"grievance_step_count": {
                "value": count,
                "display": f"{count}-step process",
                "raw_match": f"Steps {sorted(steps)} found in text",
                "confidence": 0.95,
            }}
    return None


def extract_no_strike_flag(text: str) -> dict | None:
    """Boolean: article exists with no_strike category = clause exists."""
    # The category gating already confirms this is a no-strike article.
    # Just verify the text actually mentions strike/work stoppage.
    if re.search(r'strike|work\s+stoppage|lockout', text, re.IGNORECASE):
        return {"has_no_strike_clause": {
            "value": True,
            "display": "Yes",
            "raw_match": "No-strike article present",
            "confidence": 0.99,
        }}
    return None


def extract_probationary_period(text: str) -> dict | None:
    """Extract probationary period duration from job_security articles."""
    # Look for days near "probation"
    prob_positions = [m.start() for m in re.finditer(r'probation', text, re.IGNORECASE)]
    if not prob_positions:
        return None

    # Try days first -- allow optional ")" after number (handles "sixty (60) calendar days")
    for m in re.finditer(r'(\d+)\)?\s*(calendar\s+|working\s+|business\s+)?days?', text, re.IGNORECASE):
        days = int(m.group(1))
        if days < 10 or days > 730:
            continue
        for pp in prob_positions:
            if abs(m.start() - pp) < 300:
                qualifier = m.group(2).strip() + " " if m.group(2) else ""
                display = f"{days} {qualifier}days"
                return {"probationary_period": {
                    "value": days,
                    "unit": "days",
                    "display": display,
                    "raw_match": m.group(0).strip(),
                    "confidence": 0.93,
                }}

    # Try months -- allow optional ")" after number
    for m in re.finditer(r'(\d+)\)?\s*months?', text, re.IGNORECASE):
        months = int(m.group(1))
        if months < 1 or months > 24:
            continue
        for pp in prob_positions:
            if abs(m.start() - pp) < 300:
                return {"probationary_period": {
                    "value": months * 30,
                    "unit": "months",
                    "display": f"{months} months",
                    "raw_match": m.group(0).strip(),
                    "confidence": 0.92,
                }}

    return None


# ── Extractor registry ──────────────────────────────────────────────
# Maps category -> list of extractor functions

EXTRACTORS: dict[str, list] = {
    "duration": [extract_contract_term_years],
    "holidays": [extract_holiday_count, extract_holiday_pay_rate],
    "wages_hours": [extract_overtime_multiplier],
    "overtime": [extract_overtime_multiplier],
    "grievance": [extract_grievance_step_count],
    "no_strike": [extract_no_strike_flag],
    "job_security": [extract_probationary_period],
    "probation": [extract_probationary_period],
}


# ── Processing ──────────────────────────────────────────────────────

def process_article(section_id: int, text: str, category: str) -> dict:
    """Run all extractors for this article's category. Returns subfields dict."""
    extractors = EXTRACTORS.get(category, [])
    if not extractors:
        return {}

    subfields = {}
    for extractor_fn in extractors:
        result = extractor_fn(text)
        if result:
            subfields.update(result)

    return subfields


def main():
    parser = argparse.ArgumentParser(description="Extract sub-fields from CBA articles")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--all", action="store_true", help="All contracts")
    group.add_argument("--cba-id", type=int, help="Single contract")
    parser.add_argument("--category", help="Only process articles in this category")
    parser.add_argument("--audit", action="store_true", help="Print all extractions for review")
    parser.add_argument("--dry-run", action="store_true", help="Print only, no DB changes")
    args = parser.parse_args()

    # Build query
    conditions = ["s.detection_method = 'article_heading'"]
    params = []

    if args.cba_id:
        conditions.append("s.cba_id = %s")
        params.append(args.cba_id)

    if args.category:
        conditions.append("s.attributes->>'category' = %s")
        params.append(args.category)
    else:
        # Only process categories that have extractors
        cats = list(EXTRACTORS.keys())
        placeholders = ", ".join(["%s"] * len(cats))
        conditions.append(f"s.attributes->>'category' IN ({placeholders})")
        params.extend(cats)

    where = " AND ".join(conditions)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(f"""
                SELECT s.section_id, s.cba_id, s.section_title,
                       s.section_text, s.attributes->>'category' as category
                FROM cba_sections s
                WHERE {where}
                ORDER BY s.cba_id, s.sort_order
            """, params)
            rows = cur.fetchall()

    if not rows:
        print("No matching articles found.")
        return

    print(f"Processing {len(rows)} articles across {len(EXTRACTORS)} categories")
    print("=" * 60)

    total_extracted = 0
    total_fields = 0
    field_counts = {}

    for section_id, cba_id, title, text, category in rows:
        if not text:
            continue

        subfields = process_article(section_id, text, category)
        if not subfields:
            continue

        total_extracted += 1
        total_fields += len(subfields)

        for field_name in subfields:
            field_counts[field_name] = field_counts.get(field_name, 0) + 1

        if args.audit:
            print(f"\nCBA {cba_id:>3d} | {title[:50]:<50s} [{category}]")
            for field_name, field_data in subfields.items():
                print(f"  {field_name}: {field_data['display']}")
                print(f"    RAW: \"{field_data['raw_match'][:80]}\"")
                print(f"    confidence: {field_data['confidence']}")

    print(f"\n{'=' * 60}")
    print(f"Results: {total_extracted}/{len(rows)} articles have sub-fields ({total_fields} total fields)")
    print("\nField distribution:")
    for field, cnt in sorted(field_counts.items(), key=lambda x: -x[1]):
        print(f"  {field:<30s} {cnt:>4d}")

    if args.dry_run:
        print("\nDRY RUN -- no changes written")
        return

    if args.audit and not args.all and not args.cba_id:
        print("\nAudit complete. Use --all to write to DB.")
        return

    # Write subfields to cba_sections.attributes
    written = 0
    with get_connection() as conn:
        with conn.cursor() as cur:
            for section_id, cba_id, title, text, category in rows:
                if not text:
                    continue
                subfields = process_article(section_id, text, category)
                if not subfields:
                    continue

                # Merge into existing attributes using jsonb || operator
                cur.execute("""
                    UPDATE cba_sections
                    SET attributes = attributes || %s
                    WHERE section_id = %s
                """, [json.dumps({"subfields": subfields}), section_id])
                written += 1

            conn.commit()

    print(f"\nWritten: {written} articles updated with sub-fields")


if __name__ == "__main__":
    main()
