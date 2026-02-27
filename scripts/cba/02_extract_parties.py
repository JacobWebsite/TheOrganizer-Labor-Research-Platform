"""Script 2: Extract party names, dates, and metadata from a CBA document.

Pattern-matches on the first pages to find employer, union, dates, geography.

Usage:
    py scripts/cba/02_extract_parties.py --cba-id N
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from db_config import get_connection
from scripts.cba.models import ContractMetadata

# US states for geography detection
US_STATES = {
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
}

# Major cities for geography fallback
MAJOR_CITIES = {
    "new york", "los angeles", "chicago", "houston", "phoenix",
    "philadelphia", "san antonio", "san diego", "dallas", "san jose",
    "austin", "jacksonville", "fort worth", "columbus", "charlotte",
    "indianapolis", "san francisco", "seattle", "denver", "washington",
    "nashville", "oklahoma city", "el paso", "boston", "portland",
    "las vegas", "memphis", "louisville", "baltimore", "milwaukee",
    "albuquerque", "tucson", "fresno", "sacramento", "mesa",
    "kansas city", "atlanta", "omaha", "colorado springs", "raleigh",
    "long beach", "virginia beach", "miami", "oakland", "minneapolis",
    "tulsa", "tampa", "arlington", "new orleans", "detroit", "pittsburgh",
    "cleveland", "st. louis", "buffalo", "newark", "jersey city",
}

# Month names for date parsing
MONTHS = (
    "january|february|march|april|may|june|"
    "july|august|september|october|november|december"
)
MONTH_ABBR = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"


def extract_parties_from_text(text: str) -> ContractMetadata:
    """Extract metadata from the first ~10 pages of contract text."""
    # Work with first ~15K chars (roughly 10 pages)
    front = text[:15000]
    meta = ContractMetadata()

    _extract_party_names(front, meta)
    _extract_dates(front, meta)
    _extract_local_number(front, meta)
    _extract_geography(front, meta)
    _extract_bargaining_unit(front, meta)

    return meta


def _extract_party_names(text: str, meta: ContractMetadata) -> None:
    """Find employer and union names from 'between X and Y' patterns."""
    # Pattern: "between [EMPLOYER] and [UNION]" or similar
    between_patterns = [
        # "between X and Y" — most common
        r"(?:between|by and between)\s+(.+?)\s+(?:and|&)\s+(.+?)(?:\.|,|\n|hereinafter)",
        # "entered into by X ... and Y"
        r"entered\s+into\s+by\s+(.+?)\s+(?:and|&)\s+(.+?)(?:\.|,|\n)",
    ]

    for pattern in between_patterns:
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            party1 = _clean_party_name(m.group(1))
            party2 = _clean_party_name(m.group(2))

            # Decide which is employer vs union
            if _is_union_name(party1):
                meta.union_name = party1
                meta.employer_name = party2
            elif _is_union_name(party2):
                meta.union_name = party2
                meta.employer_name = party1
            else:
                # Default: first is employer, second is union
                meta.employer_name = party1
                meta.union_name = party2
            return

    # Fallback: "hereinafter referred to as" patterns
    employer_m = re.search(
        r'(?:hereinafter\s+(?:referred\s+to\s+as|called)\s+["\']?(?:the\s+)?)["\']?(?:Employer|Company|Management|Association)["\']?',
        text, re.IGNORECASE
    )
    union_m = re.search(
        r'(?:hereinafter\s+(?:referred\s+to\s+as|called)\s+["\']?(?:the\s+)?)["\']?(?:Union|Local|Brotherhood|Association)["\']?',
        text, re.IGNORECASE
    )
    if employer_m or union_m:
        # Look for the actual names nearby
        pass  # The between pattern is the primary strategy


def _extract_dates(text: str, meta: ContractMetadata) -> None:
    """Find effective and expiration dates."""
    # Full date pattern: Month DD, YYYY or MM/DD/YYYY
    date_re = rf"(?:(?:{MONTHS})\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}/\d{{1,2}}/\d{{4}})"

    # "effective [date]" or "effective as of [date]"
    eff_m = re.search(
        rf"effective\s+(?:as\s+of\s+|from\s+|on\s+)?({date_re})",
        text, re.IGNORECASE
    )
    if eff_m:
        meta.effective_date = eff_m.group(1).strip()

    # "shall expire on [date]" or "expiration date of [date]" or "through [date]"
    exp_patterns = [
        rf"(?:shall\s+)?expir(?:e|ation)\s+(?:on\s+|date\s+(?:of\s+)?)?({date_re})",
        rf"through\s+({date_re})",
        rf"ending\s+(?:on\s+)?({date_re})",
        rf"until\s+({date_re})",
    ]
    for pat in exp_patterns:
        exp_m = re.search(pat, text, re.IGNORECASE)
        if exp_m:
            meta.expiration_date = exp_m.group(1).strip()
            break

    # "for the period [date] through [date]"
    period_m = re.search(
        rf"for\s+the\s+period\s+({date_re})\s+(?:through|to|until)\s+({date_re})",
        text, re.IGNORECASE
    )
    if period_m:
        if not meta.effective_date:
            meta.effective_date = period_m.group(1).strip()
        if not meta.expiration_date:
            meta.expiration_date = period_m.group(2).strip()

    # Year range in title: "2022-2026"
    if not meta.effective_date:
        year_m = re.search(r"(20\d{2})\s*[-\u2013]\s*(20\d{2})", text[:3000])
        if year_m:
            meta.effective_date = f"January 1, {year_m.group(1)}"
            if not meta.expiration_date:
                meta.expiration_date = f"December 31, {year_m.group(2)}"


def _extract_local_number(text: str, meta: ContractMetadata) -> None:
    """Find union local number."""
    patterns = [
        r"Local\s+(?:No\.?\s*)?(\d+[A-Z]?(?:-\d+[A-Z]?)?)",
        r"Local\s+Union\s+(?:No\.?\s*)?(\d+[A-Z]?)",
        r"Lodge\s+(?:No\.?\s*)?(\d+)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            meta.local_number = m.group(1)
            return


def _extract_geography(text: str, meta: ContractMetadata) -> None:
    """Find state and city from coverage language or party names."""
    lower = text.lower()

    # Check for state names
    for state in sorted(US_STATES, key=len, reverse=True):
        # Look near "in the state of", "covering", "employed in", or just present
        state_patterns = [
            rf"(?:state\s+of|in|covering|located\s+in)\s+{re.escape(state)}",
            rf"(?:,\s*){re.escape(state)}(?:\s|,|\.|$)",
        ]
        for pat in state_patterns:
            if re.search(pat, lower):
                meta.state = state.title()
                break
        if meta.state:
            break

    # Check for city names
    for city in sorted(MAJOR_CITIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(city)}\b", lower):
            meta.city = city.title()
            break


def _extract_bargaining_unit(text: str, meta: ContractMetadata) -> None:
    """Find bargaining unit description."""
    patterns = [
        r"bargaining\s+unit\s+(?:consisting\s+of|comprised\s+of|includes?|shall\s+(?:consist|include|be))\s+(.{20,300}?)(?:\.|$)",
        r"employees?\s+covered\s+(?:by\s+this\s+agreement\s+)?(?:include|are|shall\s+be)\s+(.{20,300}?)(?:\.|$)",
        r"all\s+(?:full[- ]?time\s+(?:and\s+(?:regular\s+)?part[- ]?time\s+)?)?employees?\s+(?:employed|working)\s+(.{10,200}?)(?:\.|$)",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if m:
            meta.bargaining_unit = _clean_text(m.group(1))
            return


def _is_union_name(name: str) -> bool:
    """Heuristic: does this name look like a union?"""
    union_indicators = [
        "local", "union", "brotherhood", "federation", "afscme", "seiu",
        "teamsters", "ufcw", "uaw", "ibew", "iam", "iamaw", "iatse",
        "afge", "nffe", "apwu", "nalc", "nteu", "afl-cio", "aflcio",
        "workers", "employees", "laborers", "carpenters", "plumbers",
        "electricians", "nurses", "teachers", "firefighters", "police",
        "council", "district council", "joint board", "lodge",
    ]
    lower = name.lower()
    return any(ind in lower for ind in union_indicators)


def _clean_party_name(name: str) -> str:
    """Clean up a party name extracted from regex."""
    name = re.sub(r"\s+", " ", name).strip()
    name = name.strip('"\'.,;:()[]')
    # Remove leading "the"
    name = re.sub(r"^the\s+", "", name, flags=re.IGNORECASE)
    return name.strip()


def _clean_text(text: str) -> str:
    """Normalize whitespace in extracted text."""
    return re.sub(r"\s+", " ", text).strip()


def get_document_text(cba_id: int) -> str | None:
    """Retrieve full_text for a document from the database."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT full_text FROM cba_documents WHERE cba_id = %s", [cba_id])
            row = cur.fetchone()
            return row[0] if row else None


def update_document_metadata(cba_id: int, meta: ContractMetadata) -> None:
    """Update cba_documents with extracted metadata."""
    with get_connection() as conn:
        with conn.cursor() as cur:
            updates = []
            params = []
            if meta.employer_name:
                updates.append("employer_name_raw = COALESCE(employer_name_raw, %s)")
                params.append(meta.employer_name)
            if meta.union_name:
                updates.append("union_name_raw = COALESCE(union_name_raw, %s)")
                params.append(meta.union_name)
            if meta.local_number:
                updates.append("local_number = COALESCE(local_number, %s)")
                params.append(meta.local_number)
            if updates:
                params.append(cba_id)
                cur.execute(
                    f"UPDATE cba_documents SET {', '.join(updates)}, updated_at = NOW() WHERE cba_id = %s",
                    params,
                )
                conn.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract party/date metadata from CBA")
    parser.add_argument("--cba-id", type=int, required=True, help="cba_id to process")
    args = parser.parse_args()

    text = get_document_text(args.cba_id)
    if not text:
        print(f"ERROR: No full_text found for cba_id={args.cba_id}")
        sys.exit(1)

    print(f"Extracting metadata from cba_id={args.cba_id} ({len(text):,} chars)")
    meta = extract_parties_from_text(text)

    print(f"\n  Employer:        {meta.employer_name or '(not found)'}")
    print(f"  Union:           {meta.union_name or '(not found)'}")
    print(f"  Local:           {meta.local_number or '(not found)'}")
    print(f"  Effective Date:  {meta.effective_date or '(not found)'}")
    print(f"  Expiration Date: {meta.expiration_date or '(not found)'}")
    print(f"  State:           {meta.state or '(not found)'}")
    print(f"  City:            {meta.city or '(not found)'}")
    print(f"  Bargaining Unit: {meta.bargaining_unit or '(not found)'}")

    update_document_metadata(args.cba_id, meta)
    print("\n  Metadata saved to database.")


if __name__ == "__main__":
    main()
