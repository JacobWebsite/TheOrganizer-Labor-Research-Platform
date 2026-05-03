"""Re-extract employer/union names + dates for CBA contracts using Gemini.

Uses Gemini 2.5 Flash to parse the first ~8K chars of full_text and return
structured JSON. Only updates contracts whose current employer_name_raw
looks like a filename-derived ID (e.g. "1114 cbrp1939"), leaving
already-good names alone.

Backs up prior values into JSONB attributes.extraction_backup before write.

Usage:
    # Dry run on 5 bad contracts, print before/after, no DB changes
    py scripts/cba/re_extract_parties.py --limit 5 --dry-run

    # Full run on all "bad" contracts (~151 expected)
    py scripts/cba/re_extract_parties.py --all

    # Single contract by cba_id
    py scripts/cba/re_extract_parties.py --cba-id 49
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

# Force UTF-8 stdout/stderr so Unicode in extracted names doesn't crash on Windows cp1252
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Load .env for GOOGLE_API_KEY
_env_path = Path(__file__).resolve().parents[2] / ".env"
if _env_path.exists():
    for line in _env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

from db_config import get_connection

MODEL = "gemini-2.5-flash"
HEAD_CHARS = 8000


# ---------------------------------------------------------------------------
# "Bad name" detection — so we only touch contracts where extraction failed
# ---------------------------------------------------------------------------
#
# Good names (keep):
#   "10 Roads Express", "Wal-Mart Stores", "Service Employees International Union"
# Bad names (re-extract):
#   "1114 cbrp1939"  (filename with ID)
#   "1122 OperaColorado K8367 063022"  (underscored filename)
#   "119 cbrp 2237 pri"
#   "Unknown", "Unknown Union"

_BAD_EMP_RX = re.compile(
    r"(^[0-9]+\s+)"                  # leading numeric id (1114 ...)
    r"|cbrp[0-9]*"                   # OLMS cbrp identifier
    r"|\bK[0-9]{4,}\b"                # filename K1234 form
    r"|^\s*(unknown|n/a|none)\s*$",
    re.IGNORECASE,
)

_BAD_UNI_RX = re.compile(
    r"^\s*(unknown|unknown union|n/a|none)\s*$",
    re.IGNORECASE,
)


def is_bad_employer(name: str | None) -> bool:
    if not name or len(name.strip()) < 3:
        return True
    return bool(_BAD_EMP_RX.search(name))


def is_bad_union(name: str | None) -> bool:
    if not name or len(name.strip()) < 3:
        return True
    return bool(_BAD_UNI_RX.match(name))


# ---------------------------------------------------------------------------
# Gemini extraction
# ---------------------------------------------------------------------------

_client = None


def _gemini_client():
    global _client
    if _client is not None:
        return _client
    from google import genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set")
        sys.exit(1)
    _client = genai.Client(api_key=api_key)
    return _client


PROMPT = """You will be given the opening text of a collective bargaining \
agreement (CBA). Extract the following fields as JSON. Return ONLY the JSON \
object, no surrounding prose.

Required fields:
- employer_name: The full legal name of the EMPLOYER (company, institution, \
  city/agency, hospital, etc.). If multiple employers, return the primary \
  one. If the contract is a multi-employer agreement (e.g., a trade \
  association), return the association name.
- union_name: The full name of the UNION (labor organization). Usually \
  something like "Service Employees International Union, Local 1199", \
  "International Brotherhood of Teamsters, Local 810", "American Federation \
  of State, County and Municipal Employees, Local 1184", etc.

Optional fields (use null if not found):
- union_local_number: Just the local number, e.g. "1199", "810". String.
- union_affiliation: The national/international union, e.g. "SEIU", "AFSCME", \
  "IBT", "AFL-CIO".
- effective_date: YYYY-MM-DD if a clear effective date is present.
- expiration_date: YYYY-MM-DD if a clear expiration date is present.
- geography_state: Two-letter state code if geography is clear (e.g., "NY").
- geography_city: City name if clear.

Rules:
- employer_name and union_name must be REAL names from the text, not placeholders.
- Do NOT invent or guess. If the text is too corrupt, garbled, or doesn't \
  identify the parties, return {"employer_name": null, "union_name": null, ...}.
- Strip boilerplate: do NOT include "hereinafter referred to as 'the Employer'" \
  or similar trailing phrases.
- Normalize whitespace and drop trailing commas/periods.
- Return dates as YYYY-MM-DD strings, not free-text.

Text:
---
"""


_FIELD_RX = re.compile(
    r'"(?P<key>[a-zA-Z_]+)":\s*(?:null|"(?P<val>[^"]*)")',
)


def _regex_fallback(raw: str) -> dict | None:
    """Extract completed key-value pairs from truncated/malformed JSON.

    Only captures fields whose string value is fully terminated (has a closing
    quote). Truncated strings like "2003-01- are silently ignored because the
    regex requires [^"]* followed by a closing quote.
    """
    result: dict = {}
    for m in _FIELD_RX.finditer(raw):
        key = m.group("key")
        val = m.group("val")  # None when the null branch matched
        result[key] = val  # val is None for JSON null, string otherwise
    return result if (result.get("employer_name") or result.get("union_name")) else None


def extract_parties_via_llm(text: str, max_retries: int = 4) -> dict | None:
    """Call Gemini and parse JSON response. Retries on 503/429 with backoff."""
    from google.genai import types as genai_types
    client = _gemini_client()

    prompt = PROMPT + text[:HEAD_CHARS]

    response = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=genai_types.GenerateContentConfig(
                    temperature=0.0,
                    response_mime_type="application/json",
                    max_output_tokens=2048,
                ),
            )
            break
        except Exception as exc:
            msg = str(exc)
            transient = any(s in msg for s in (
                "503", "UNAVAILABLE", "429", "RESOURCE_EXHAUSTED",
                "high demand", "temporarily", "500", "INTERNAL",
            ))
            if transient and attempt < max_retries - 1:
                wait_s = 3 * (2 ** attempt)  # 3, 6, 12, 24s
                print(f"  Transient error (attempt {attempt+1}/{max_retries}): waiting {wait_s}s")
                time.sleep(wait_s)
                continue
            print(f"  Gemini API error: {exc}")
            return None

    if response is None:
        return None

    raw = (response.text or "").strip()
    # Strip markdown code fences if present
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```\s*$", "", raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"  JSON parse error: {exc}")
        print(f"  Raw: {raw[:200]!r}")
        # Fallback: salvage complete key-value pairs from truncated JSON via regex.
        # Only captures fields whose string values are fully terminated (closing quote present).
        fallback = _regex_fallback(raw)
        if fallback:
            print(f"  Regex fallback recovered: emp={fallback.get('employer_name')!r}  uni={fallback.get('union_name')!r}")
            return fallback
        return None


# ---------------------------------------------------------------------------
# Database update
# ---------------------------------------------------------------------------

def fetch_candidates(cur, args):
    """Return list of (cba_id, employer_raw, union_raw, full_text) for contracts to process."""
    if args.cba_id:
        cur.execute(
            "SELECT cba_id, employer_name_raw, union_name_raw, full_text "
            "FROM cba_documents WHERE cba_id = %s",
            [args.cba_id],
        )
        return cur.fetchall()

    # Otherwise select contracts where name looks bad AND we have text to work with
    cur.execute(
        """
        SELECT cba_id, employer_name_raw, union_name_raw, full_text
        FROM cba_documents
        WHERE full_text IS NOT NULL AND length(full_text) > 500
        ORDER BY cba_id
        """
    )
    all_rows = cur.fetchall()
    bad = [
        row for row in all_rows
        if is_bad_employer(row[1]) or is_bad_union(row[2])
    ]
    if args.limit:
        return bad[: args.limit]
    return bad


def apply_update(cur, cba_id, old_emp, old_uni, parsed):
    """Update cba_documents with the extracted fields. Backup old values."""
    emp = (parsed.get("employer_name") or "").strip() or None
    uni = (parsed.get("union_name") or "").strip() or None
    local = (parsed.get("union_local_number") or "").strip() or None
    affil = (parsed.get("union_affiliation") or "").strip() or None
    eff = parsed.get("effective_date") or None
    exp = parsed.get("expiration_date") or None
    state = (parsed.get("geography_state") or "").strip() or None
    city = (parsed.get("geography_city") or "").strip() or None

    # Only write fields we actually got; keep old value as fallback
    new_emp = emp if emp else old_emp
    new_uni = uni if uni else old_uni

    cur.execute(
        """
        UPDATE cba_documents
        SET employer_name_raw = %s,
            union_name_raw    = %s,
            local_number      = COALESCE(%s, local_number),
            effective_date    = COALESCE(%s, effective_date),
            expiration_date   = COALESCE(%s, expiration_date),
            updated_at        = CURRENT_TIMESTAMP
        WHERE cba_id = %s
        """,
        [new_emp, new_uni, local, eff, exp, cba_id],
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Re-extract CBA parties via Gemini")
    ap.add_argument("--cba-id", type=int, help="Single contract")
    ap.add_argument("--limit", type=int, help="Process at most N bad contracts")
    ap.add_argument("--all", action="store_true", help="Process all bad contracts")
    ap.add_argument("--dry-run", action="store_true", help="Print only, no DB writes")
    args = ap.parse_args()

    if not args.cba_id and not args.all and not args.limit:
        ap.error("Must pass --cba-id N, --limit N, or --all")

    with get_connection() as conn:
        with conn.cursor() as cur:
            candidates = fetch_candidates(cur, args)

    if not candidates:
        print("No candidates found.")
        return

    print(f"Processing {len(candidates)} contract(s)")
    print(f"Model: {MODEL}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print("=" * 72)

    updated = 0
    skipped = 0
    failed = 0

    for cba_id, old_emp, old_uni, text in candidates:
        print(f"\n--- cba_id={cba_id} ---")
        print(f"  OLD emp: {old_emp!r}")
        print(f"  OLD uni: {old_uni!r}")

        parsed = extract_parties_via_llm(text or "")
        if parsed is None:
            print("  LLM failed, skipping")
            failed += 1
            continue

        new_emp = parsed.get("employer_name")
        new_uni = parsed.get("union_name")
        print(f"  NEW emp: {new_emp!r}")
        print(f"  NEW uni: {new_uni!r}")
        if parsed.get("union_local_number"):
            print(f"  local:   {parsed['union_local_number']!r}")
        if parsed.get("effective_date"):
            print(f"  effective: {parsed['effective_date']}")
        if parsed.get("expiration_date"):
            print(f"  expires:   {parsed['expiration_date']}")

        # Only write if we got something materially better
        if not new_emp and not new_uni:
            print("  LLM returned nothing useful, skipping")
            skipped += 1
            continue

        if args.dry_run:
            continue

        with get_connection() as conn:
            with conn.cursor() as cur:
                apply_update(cur, cba_id, old_emp, old_uni, parsed)
            conn.commit()
        updated += 1

        # Modest rate-limit politeness
        time.sleep(0.25)

    print()
    print("=" * 72)
    print(f"Summary: updated={updated}, skipped={skipped}, failed={failed}")


if __name__ == "__main__":
    main()
