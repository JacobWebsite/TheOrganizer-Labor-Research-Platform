"""
Extract employee counts from SEC 10-K filings using edgartools + Gemini.

Usage:
    py scripts/etl/extract_sec_employee_counts.py [--limit N] [--dry-run] [--validate]

Requirements:
    pip install edgartools
    GOOGLE_API_KEY in .env
    EDGAR_IDENTITY in .env (e.g., "Labor Data Platform research@example.com")
"""

import argparse
import json
import os
import sys
import time

# Project root setup
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), ".env"))

from db_config import get_connection

CHECKPOINT_FILE = os.path.join(os.path.dirname(__file__), ".employee_extract_checkpoint.json")
BATCH_SIZE = 50


def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {"completed_ciks": [], "stats": {"success": 0, "no_data": 0, "errors": 0}}


def save_checkpoint(state):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(state, f)


def get_candidates(conn, limit=None, exclude_ciks=None):
    """Find CIKs with revenue but no employee_count."""
    cur = conn.cursor()
    cur.execute("""
        SELECT x.cik, s.company_name,
               MAX(x.fiscal_year_end) AS latest_fy,
               MAX(x.revenue) AS max_revenue
        FROM sec_xbrl_financials x
        JOIN sec_companies s ON s.cik::int = x.cik
        WHERE x.employee_count IS NULL
          AND x.fiscal_year_end >= '2020-01-01'
          AND x.revenue IS NOT NULL
        GROUP BY x.cik, s.company_name
        ORDER BY max_revenue DESC NULLS LAST
    """)
    rows = cur.fetchall()
    cur.close()

    if exclude_ciks:
        exclude_set = set(exclude_ciks)
        rows = [r for r in rows if r[0] not in exclude_set]

    if limit:
        rows = rows[:limit]

    return rows


def fetch_10k_text(cik, company_name):
    """Fetch the latest 10-K text excerpt using edgartools."""
    from edgar import Company

    try:
        company = Company(cik)
        filings = company.get_filings(form="10-K")
        if not filings or len(filings) == 0:
            # Try 10-K/A (amendment)
            filings = company.get_filings(form="10-K/A")
        if not filings or len(filings) == 0:
            return None, None

        latest = filings[0]
        filing_date = str(latest.filing_date) if hasattr(latest, "filing_date") else None

        # Get the filing document text
        try:
            text = latest.text()
        except Exception:
            try:
                # Fallback: try getting the primary document
                doc = latest.document
                text = doc.text() if doc else None
            except Exception:
                return None, filing_date

        if not text:
            return None, filing_date

        # Extract Item 1 section (where employee count is typically found)
        text_upper = text.upper()
        item1_start = -1
        for marker in ["ITEM 1.", "ITEM 1 ", "ITEM\xa01."]:
            idx = text_upper.find(marker)
            if idx >= 0:
                item1_start = idx
                break

        if item1_start >= 0:
            # Take from Item 1 to Item 1A or Item 2 (whichever comes first)
            section = text[item1_start:item1_start + 50000]
            for end_marker in ["ITEM 1A", "ITEM 2", "ITEM\xa01A", "ITEM\xa02"]:
                end_idx = section.upper().find(end_marker, 100)
                if end_idx > 0:
                    section = section[:end_idx]
                    break
            return section[:8000], filing_date
        else:
            # Fallback: return first 8000 chars
            return text[:8000], filing_date

    except Exception as exc:
        print(f"  edgartools error for CIK {cik} ({company_name}): {exc}")
        return None, None


def extract_employee_count(text, company_name):
    """Use Gemini to extract employee count from 10-K text."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set in .env")
        sys.exit(1)

    from google import genai

    client = genai.Client(api_key=api_key)

    prompt = (
        f"Extract the total number of employees for {company_name} from this SEC 10-K filing excerpt.\n"
        "Return ONLY a JSON object with no other text:\n"
        '{"employee_count": <integer or null>, "as_of_date": "<YYYY-MM-DD or null>", '
        '"confidence": "high" | "medium" | "low", "excerpt": "<the sentence mentioning employees>"}\n'
        "If no employee count is found, return: "
        '{"employee_count": null, "confidence": "low", "excerpt": null}\n\n'
        f"Filing excerpt:\n{text[:5000]}"
    )

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3].strip()
        if raw.startswith("json"):
            raw = raw[4:].strip()

        return json.loads(raw)
    except json.JSONDecodeError:
        print(f"  Gemini returned non-JSON for {company_name}: {raw[:100]}")
        return None
    except Exception as exc:
        print(f"  Gemini error for {company_name}: {exc}")
        return None


def update_employee_count(conn, cik, latest_fy, count, tag="LLM_10K_EXTRACTION"):
    """Write extracted employee count to sec_xbrl_financials."""
    cur = conn.cursor()
    cur.execute("""
        UPDATE sec_xbrl_financials
        SET employee_count = %s, employee_count_tag = %s
        WHERE cik = %s AND fiscal_year_end = %s
    """, [count, tag, cik, latest_fy])
    conn.commit()
    cur.close()


def validate_against_xbrl(conn):
    """Compare LLM-extracted counts against XBRL-reported counts for the same companies."""
    cur = conn.cursor()
    cur.execute("""
        SELECT x1.cik, s.company_name,
               x1.employee_count AS llm_count, x1.fiscal_year_end AS llm_fy,
               x2.employee_count AS xbrl_count, x2.fiscal_year_end AS xbrl_fy
        FROM sec_xbrl_financials x1
        JOIN sec_xbrl_financials x2 ON x1.cik = x2.cik
        JOIN sec_companies s ON s.cik::int = x1.cik
        WHERE x1.employee_count_tag = 'LLM_10K_EXTRACTION'
          AND x2.employee_count_tag != 'LLM_10K_EXTRACTION'
          AND x1.employee_count IS NOT NULL
          AND x2.employee_count IS NOT NULL
          AND x2.employee_count > 0
        ORDER BY ABS(x1.employee_count::float / x2.employee_count - 1) DESC
    """)
    rows = cur.fetchall()
    cur.close()

    if not rows:
        print("No overlap between LLM-extracted and XBRL-reported counts for validation.")
        return

    print(f"\nValidation: {len(rows)} companies with both LLM and XBRL counts")
    print(f"{'CIK':>10} {'Company':<40} {'LLM':>10} {'XBRL':>10} {'Diff%':>8}")
    print("-" * 82)

    discrepancies = 0
    for r in rows[:30]:
        ratio = r[2] / r[4] if r[4] else 0
        diff_pct = (ratio - 1) * 100
        flag = " **" if abs(diff_pct) > 100 else ""
        print(f"{r[0]:>10} {r[1][:40]:<40} {r[2]:>10,} {r[4]:>10,} {diff_pct:>+7.1f}%{flag}")
        if abs(diff_pct) > 100:
            discrepancies += 1

    print(f"\n{discrepancies} companies with >2x discrepancy out of {len(rows)} validated")


def main():
    parser = argparse.ArgumentParser(description="Extract employee counts from SEC 10-K filings")
    parser.add_argument("--limit", type=int, default=None, help="Max companies to process")
    parser.add_argument("--dry-run", action="store_true", help="Show candidates without processing")
    parser.add_argument("--validate", action="store_true", help="Validate LLM vs XBRL counts")
    parser.add_argument("--reset", action="store_true", help="Reset checkpoint file")
    args = parser.parse_args()

    # Set EDGAR identity
    identity = os.environ.get("EDGAR_IDENTITY", "")
    if not identity and not args.dry_run and not args.validate:
        print("WARNING: EDGAR_IDENTITY not set. SEC may rate-limit requests.")
        print("Set EDGAR_IDENTITY='Your Name email@example.com' in .env")

    if identity:
        from edgar import set_identity
        set_identity(identity)

    conn = get_connection()

    if args.validate:
        validate_against_xbrl(conn)
        conn.close()
        return

    if args.reset and os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("Checkpoint reset.")

    state = load_checkpoint()
    candidates = get_candidates(conn, limit=args.limit, exclude_ciks=state["completed_ciks"])

    print(f"Candidates: {len(candidates)} companies with revenue but no employee_count")
    if args.dry_run:
        for i, row in enumerate(candidates[:20]):
            print(f"  {i+1}. CIK {row[0]} - {row[1]} (latest FY: {row[2]})")
        if len(candidates) > 20:
            print(f"  ... and {len(candidates) - 20} more")
        conn.close()
        return

    if not candidates:
        print("Nothing to process.")
        conn.close()
        return

    print(f"Processing {len(candidates)} companies (checkpoint has {len(state['completed_ciks'])} done)")
    print()

    for i, row in enumerate(candidates):
        cik, name, latest_fy = row[0], row[1], row[2]
        print(f"[{i+1}/{len(candidates)}] CIK {cik} - {name}...")

        # Fetch 10-K text
        text, filing_date = fetch_10k_text(cik, name)
        time.sleep(0.15)  # SEC rate limit: 10 req/sec

        if not text:
            print("  No 10-K text found")
            state["stats"]["no_data"] += 1
            state["completed_ciks"].append(cik)
            if (i + 1) % BATCH_SIZE == 0:
                save_checkpoint(state)
            continue

        # Extract via Gemini
        result = extract_employee_count(text, name)
        time.sleep(0.5)  # Gemini rate spacing

        if result and result.get("employee_count"):
            count = result["employee_count"]
            confidence = result.get("confidence", "unknown")
            excerpt = (result.get("excerpt") or "")[:100]
            print(f"  -> {count:,} employees (confidence: {confidence})")
            if excerpt:
                print(f"     \"{excerpt}\"")

            update_employee_count(conn, cik, latest_fy, count)
            state["stats"]["success"] += 1
        elif result:
            print("  No employee count found in filing")
            state["stats"]["no_data"] += 1
        else:
            print("  Extraction failed")
            state["stats"]["errors"] += 1

        state["completed_ciks"].append(cik)

        if (i + 1) % BATCH_SIZE == 0:
            save_checkpoint(state)
            s = state["stats"]
            print(f"\n  -- Checkpoint: {s['success']} extracted, {s['no_data']} no data, {s['errors']} errors --\n")

    save_checkpoint(state)
    s = state["stats"]
    print(f"\nDone. {s['success']} extracted, {s['no_data']} no data, {s['errors']} errors")
    print(f"Total processed: {len(state['completed_ciks'])}")

    conn.close()


if __name__ == "__main__":
    main()
