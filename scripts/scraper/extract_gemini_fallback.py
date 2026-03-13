"""
Gemini API fallback extraction for profiles with 0 employers after all other tiers.

Uses Google Gemini 2.5 Flash to extract employer names from raw text.

Usage:
    py scripts/scraper/extract_gemini_fallback.py
    py scripts/scraper/extract_gemini_fallback.py --dry-run
    py scripts/scraper/extract_gemini_fallback.py --limit 10
    py scripts/scraper/extract_gemini_fallback.py --profile-id 42
"""
import sys
import os
import json
import time
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection
from scripts.scraper.parse_structured import clean_employer_name, guess_sector


# ── Config ────────────────────────────────────────────────────────────────

MAX_INPUT_CHARS = 8000
RATE_LIMIT_SECS = 2.0

EXTRACTION_PROMPT = """You are analyzing text from a labor union website. Extract the following:

1. **employers** - Organizations/companies/agencies this union represents workers at. Return as a list of objects with:
   - "name": employer name (official, clean)
   - "confidence": 0.0 to 1.0
   - "evidence": brief quote from text

2. **membership_count** - Number of members if mentioned (integer or null)

3. **has_contracts_page** - true if the text mentions contracts/CBAs being available

Return ONLY valid JSON in this exact format:
{
  "employers": [{"name": "...", "confidence": 0.8, "evidence": "..."}],
  "membership_count": null,
  "has_contracts_page": false
}

TEXT TO ANALYZE:
"""


# ── Gemini Client ────────────────────────────────────────────────────────

def _get_gemini_client():
    """Get Gemini client. Returns (client, types) or (None, None)."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not set in environment / .env")
        return None, None

    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=api_key)
        return client, types
    except ImportError:
        print("ERROR: google-genai not installed")
        return None, None


def call_gemini(client, types, text):
    """Call Gemini to extract employer data from text."""
    truncated = text[:MAX_INPUT_CHARS]
    prompt = EXTRACTION_PROMPT + truncated

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=[types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)],
        )],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=4096,
            temperature=0.0,
        ),
    )

    candidate = response.candidates[0] if response.candidates else None
    if not candidate or not candidate.content or not candidate.content.parts:
        return None

    raw = candidate.content.parts[0].text.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        # Try to salvage partial JSON
        try:
            # Find last complete object
            last_brace = raw.rfind('}')
            if last_brace > 0:
                # Close any open arrays/objects
                trimmed = raw[:last_brace + 1]
                if trimmed.count('[') > trimmed.count(']'):
                    trimmed += ']'
                if trimmed.count('{') > trimmed.count('}'):
                    trimmed += '}'
                return json.loads(trimmed)
        except json.JSONDecodeError:
            pass
        return None


# ── Main Logic ───────────────────────────────────────────────────────────

def get_qualifying_profiles(conn, profile_id=None):
    """Get profiles with 0 employers that haven't used Gemini yet."""
    cur = conn.cursor()

    if profile_id:
        cur.execute("""
            SELECT p.id, p.union_name, p.state, p.raw_text, p.website_url
            FROM web_union_profiles p
            WHERE p.id = %s
              AND p.raw_text IS NOT NULL
        """, (profile_id,))
    else:
        cur.execute("""
            SELECT p.id, p.union_name, p.state, p.raw_text, p.website_url
            FROM web_union_profiles p
            LEFT JOIN web_union_employers e ON e.web_profile_id = p.id
            WHERE p.scrape_status IN ('FETCHED', 'EXTRACTED')
              AND p.gemini_used IS NOT TRUE
              AND p.raw_text IS NOT NULL
            GROUP BY p.id, p.union_name, p.state, p.raw_text, p.website_url
            HAVING COUNT(e.id) = 0
            ORDER BY p.id
        """)

    return cur.fetchall()


def extract_with_gemini(conn, profiles, dry_run=False, limit=None):
    """Run Gemini extraction on qualifying profiles."""
    client, types = _get_gemini_client()
    if not client and not dry_run:
        return

    if limit:
        profiles = profiles[:limit]

    print(f"Gemini fallback: {len(profiles)} qualifying profiles\n")

    total_employers = 0
    total_tokens_est = 0
    processed = 0

    cur = conn.cursor()

    for pid, name, state, raw_text, website_url in profiles:
        text_len = len(raw_text or '')
        tokens_est = text_len // 4
        total_tokens_est += min(tokens_est, MAX_INPUT_CHARS // 4)

        print(f"[{pid}] {name} ({text_len:,} chars)")

        if dry_run:
            print(f"  DRY RUN: would send ~{min(text_len, MAX_INPUT_CHARS):,} chars to Gemini")
            continue

        # Combine all text sources
        all_text = raw_text or ''

        try:
            time.sleep(RATE_LIMIT_SECS)
            result = call_gemini(client, types, all_text)
        except Exception as e:
            print(f"  Gemini error: {e}")
            cur.execute("""
                UPDATE web_union_profiles SET gemini_used = TRUE WHERE id = %s
            """, (pid,))
            conn.commit()
            continue

        if not result:
            print(f"  No result from Gemini")
            cur.execute("""
                UPDATE web_union_profiles SET gemini_used = TRUE WHERE id = %s
            """, (pid,))
            conn.commit()
            continue

        # Insert employers
        employers = result.get('employers', [])
        inserted = 0
        for emp in employers:
            emp_name = clean_employer_name(emp.get('name', ''))
            if not emp_name:
                continue

            sector = guess_sector(emp_name)
            confidence = min(float(emp.get('confidence', 0.5)), 0.5)  # Cap at 0.5

            try:
                cur.execute("""
                    INSERT INTO web_union_employers
                        (web_profile_id, employer_name, employer_name_clean, state, sector,
                         source_url, extraction_method, confidence_score,
                         source_element, updated_at)
                    VALUES (%s, %s, %s, %s, %s, %s, 'gemini_fallback', %s, 'gemini', NOW())
                    ON CONFLICT (web_profile_id, employer_name_clean) DO NOTHING
                """, (pid, emp_name, emp_name, state, sector, website_url, confidence))
                inserted += cur.rowcount
            except Exception:
                pass

        # Insert membership count if found
        mem_count = result.get('membership_count')
        if mem_count and isinstance(mem_count, (int, float)) and 50 <= mem_count <= 5_000_000:
            try:
                cur.execute("""
                    INSERT INTO web_union_membership
                        (web_profile_id, member_count, member_count_source, count_type, source_url)
                    VALUES (%s, %s, 'gemini_fallback', 'approximate', %s)
                """, (pid, int(mem_count), website_url))
            except Exception:
                pass

        # Mark as processed
        cur.execute("""
            UPDATE web_union_profiles SET gemini_used = TRUE WHERE id = %s
        """, (pid,))
        conn.commit()

        total_employers += inserted
        processed += 1
        print(f"  Extracted: {inserted}/{len(employers)} employers")

    # Summary
    print(f"\n{'='*60}")
    print(f"GEMINI FALLBACK COMPLETE")
    print(f"{'='*60}")
    print(f"  Profiles processed: {processed}")
    print(f"  Employers inserted: {total_employers}")
    print(f"  Est. input tokens:  ~{total_tokens_est:,}")
    print(f"  Est. cost:          ~${total_tokens_est * 0.15 / 1_000_000:.4f} (input only)")

    return total_employers


# ── CLI ──────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description='Gemini fallback extraction')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    parser.add_argument('--limit', type=int, help='Max profiles to process')
    parser.add_argument('--profile-id', type=int, help='Process single profile')
    args = parser.parse_args()

    conn = get_connection()
    try:
        profiles = get_qualifying_profiles(conn, args.profile_id)
        extract_with_gemini(conn, profiles, dry_run=args.dry_run, limit=args.limit)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
