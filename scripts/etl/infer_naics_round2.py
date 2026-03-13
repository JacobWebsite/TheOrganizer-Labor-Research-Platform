"""Infer missing NAICS from employer names -- Round 2.

Three strategies in priority order:
  A) Brand lookup (well-known companies -> specific NAICS)
  B) Extended keyword patterns (categories not covered by round 1)
  C) Government broadening (public entities with specific sub-codes)

Rules:
- Only rows where f7_employers_deduped.naics IS NULL
- Brand > Keyword > Government priority
- Skip ambiguous (multiple NAICS within same strategy)
- Dry-run by default, --commit to persist
"""
import argparse
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from db_config import get_connection


# ---------------------------------------------------------------------------
# Strategy A: Brand Lookup
# ---------------------------------------------------------------------------
# Map well-known brand substrings -> 6-digit NAICS.
# Short names (<=4 chars) require exact match after normalization.

BRAND_NAICS = {
    # Food service / catering
    "STARBUCKS": "722515",
    "ARAMARK": "722310",
    "SODEXO": "722310",
    "COMPASS GROUP": "722310",
    "CHARTWELLS": "722310",
    "EUREST": "722310",
    "CANTEEN": "722310",
    "MORRISON HEALTHCARE": "722310",
    "MCCORMICK AND SCHMICK": "722511",
    "OLIVE GARDEN": "722511",
    "APPLEBEE": "722511",
    "DENNY": "722511",
    "IHOP": "722511",
    "CHILI": "722511",
    "CRACKER BARREL": "722511",
    "RED LOBSTER": "722511",
    "OUTBACK STEAKHOUSE": "722511",
    "PANERA": "722515",
    "CHIPOTLE": "722513",
    "TACO BELL": "722513",
    "BURGER KING": "722513",
    "WENDY": "722513",
    "POPEYE": "722513",
    "SUBWAY": "722513",
    "DOMINO": "722513",
    "PIZZA HUT": "722513",
    "PAPA JOHN": "722513",
    "DUNKIN": "722515",
    "TIM HORTON": "722515",
    "PEET": "722515",
    # Car rental
    "HERTZ": "532111",
    "AVIS": "532111",
    "BUDGET RENT": "532111",
    "ENTERPRISE RENT": "532111",
    "NATIONAL CAR RENTAL": "532111",
    # Parcel / courier
    "UNITED PARCEL": "492110",
    "FEDEX": "492110",
    "FEDERAL EXPRESS": "492110",
    "DHL": "492110",
    # Automotive manufacturing
    "FORD MOTOR": "336111",
    "GENERAL MOTORS": "336111",
    "CHRYSLER": "336111",
    "STELLANTIS": "336111",
    "TOYOTA": "336111",
    "HONDA": "336111",
    "NISSAN": "336111",
    "SUBARU": "336111",
    "TESLA": "336111",
    "VOLVO": "336111",
    "BMW": "336111",
    "VOLKSWAGEN": "336111",
    "MERCEDES": "336111",
    "HYUNDAI": "336111",
    "KIA": "336111",
    # Transit / school bus
    "FIRST STUDENT": "485410",
    "FIRST TRANSIT": "485113",
    "FIRST GROUP": "485113",
    "NATIONAL EXPRESS": "485410",
    "DURHAM SCHOOL": "485410",
    # Facility services
    "ABM INDUSTRIES": "561720",
    "ABM JANITORIAL": "561720",
    "ABM FACILITY": "561720",
    # Uniform / linen
    "CINTAS": "812332",
    "VESTIS": "812332",
    "UNITEX": "812332",
    "UNIFIRST": "812332",
    "ALSCO": "812332",
    "ARAMARK UNIFORM": "812332",
    # Grocery / retail
    "WALMART": "445110",
    "KROGER": "445110",
    "ALBERTSON": "445110",
    "SAFEWAY": "445110",
    "PUBLIX": "445110",
    "AHOLD": "445110",
    "STOP AND SHOP": "445110",
    "GIANT FOOD": "445110",
    "FOOD LION": "445110",
    "TRADER JOE": "445110",
    "WHOLE FOODS": "445110",
    "ALDI": "445110",
    "WEGMAN": "445110",
    "MEIJER": "445110",
    "HEB": "445110",
    "TARGET": "452210",
    "COSTCO": "452311",
    "HOME DEPOT": "444110",
    "LOWE": "444110",
    "WALGREEN": "446110",
    "CVS": "446110",
    "RITE AID": "446110",
    "DOLLAR GENERAL": "452319",
    "DOLLAR TREE": "452319",
    "FAMILY DOLLAR": "452319",
    # Telecom
    "AT&T": "517311",
    "VERIZON": "517311",
    "T-MOBILE": "517312",
    "SPRINT": "517312",
    "COMCAST": "517311",
    "CHARTER COMMUNICATION": "517311",
    "SPECTRUM": "517311",
    "CENTURYLINK": "517311",
    "LUMEN": "517311",
    "FRONTIER COMMUNICATION": "517311",
    # Airlines
    "AMERICAN AIRLINES": "481111",
    "DELTA AIR": "481111",
    "UNITED AIRLINES": "481111",
    "SOUTHWEST AIRLINES": "481111",
    "JETBLUE": "481111",
    "SPIRIT AIRLINES": "481111",
    "ALASKA AIR": "481111",
    # Railroad
    "UNION PACIFIC": "482111",
    "BNSF": "482111",
    "CSX": "482111",
    "NORFOLK SOUTHERN": "482111",
    "AMTRAK": "482111",
    # Hotels
    "MARRIOTT": "721110",
    "HILTON": "721110",
    "HYATT": "721110",
    "SHERATON": "721110",
    "WESTIN": "721110",
    "INTERCONTINENTAL": "721110",
    "HOLIDAY INN": "721110",
    "WYNDHAM": "721110",
    "BEST WESTERN": "721110",
    "DOUBLETREE": "721110",
    "HAMPTON INN": "721110",
    "FAIRFIELD INN": "721110",
    "COURTYARD BY MARRIOTT": "721110",
    # Healthcare systems
    "KAISER": "622110",
    "HCA HEALTHCARE": "622110",
    "ASCENSION": "622110",
    "COMMONSPIRIT": "622110",
    "TRINITY HEALTH": "622110",
    "ADVOCATE": "622110",
    "PROVIDENCE HEALTH": "622110",
    "INTERMOUNTAIN": "622110",
    "SUTTER HEALTH": "622110",
    "BANNER HEALTH": "622110",
    "BEAUMONT HEALTH": "622110",
    "ATRIUM HEALTH": "622110",
    "BAYLOR SCOTT": "622110",
    "CEDARS SINAI": "622110",
    "CLEVELAND CLINIC": "622110",
    "MAYO CLINIC": "622110",
    "MOUNT SINAI": "622110",
    "NYU LANGONE": "622110",
    "PARTNERS HEALTHCARE": "622110",
    # Waste
    "WASTE MANAGEMENT": "562111",
    "REPUBLIC SERVICES": "562111",
    "CASELLA WASTE": "562111",
    "WASTE CONNECTION": "562111",
    # Security
    "SECURITAS": "561612",
    "ALLIED UNIVERSAL": "561612",
    "G4S": "561612",
    "GARDA WORLD": "561612",
    # Staffing
    "KELLY SERVICES": "561320",
    "ROBERT HALF": "561320",
    "MANPOWER": "561320",
    "ADECCO": "561320",
    "RANDSTAD": "561320",
    # Steel / metals
    "US STEEL": "331110",
    "UNITED STATES STEEL": "331110",
    "NUCOR": "331110",
    "ARCELOR": "331110",
    "ALCOA": "331313",
    # Aerospace / defense
    "BOEING": "336411",
    "LOCKHEED": "336411",
    "NORTHROP GRUMMAN": "336411",
    "RAYTHEON": "336411",
    "GENERAL DYNAMICS": "336411",
    "BAE SYSTEMS": "336411",
    "L3HARRIS": "334511",
    # Auto parts
    "DANA": "336350",
    "DELPHI": "336390",
    "BORG WARNER": "336390",
    "LEAR CORP": "336360",
    "MAGNA": "336390",
}

_STRIP_SUFFIXES = re.compile(
    r"\b(INC|LLC|CORP|CORPORATION|CO|COMPANY|LTD|LP|LLP|PC|PA|PLLC|"
    r"NA|NV|SA|AG|GMBH|PLC|DBA|THE)\b",
    re.IGNORECASE,
)
_COLLAPSE = re.compile(r"[^A-Z0-9 ]")


def _normalize_brand(name: str) -> str:
    """Aggressive normalization for brand matching."""
    text = (name or "").upper().strip()
    text = _STRIP_SUFFIXES.sub("", text)
    text = _COLLAPSE.sub("", text)
    return " ".join(text.split())


def match_brand(name: str) -> str | None:
    """Return NAICS if name matches a known brand, else None."""
    norm = _normalize_brand(name)
    if not norm:
        return None
    for brand, naics in BRAND_NAICS.items():
        brand_norm = _normalize_brand(brand)
        if len(brand_norm) <= 4:
            # Short names: require exact match
            if norm == brand_norm:
                return naics
        else:
            if brand_norm in norm:
                return naics
    return None


# ---------------------------------------------------------------------------
# Strategy B: Extended Keyword Patterns (not in round 1)
# ---------------------------------------------------------------------------

KEYWORD_RULES_R2 = {
    "parking": {"naics": "812930", "patterns": [
        r"\bparking\b", r"\bgarage[s]?\b(?!.*door)", r"\bvalet\b",
    ]},
    "glass": {"naics": "327211", "patterns": [
        r"\bglass\b(?!.*eye)", r"\bglazier\b", r"\bglazing\b",
    ]},
    "uniform_linen": {"naics": "812332", "patterns": [
        r"\buniform\b", r"\blinen\b", r"\blaundry service\b", r"\btextile rental\b",
    ]},
    "performing_arts": {"naics": "711110", "patterns": [
        r"\btheater\b", r"\btheatre\b", r"\bopera\b", r"\bsymphony\b",
        r"\borchestra\b", r"\bballet\b", r"\bperforming arts\b",
    ]},
    "funeral": {"naics": "812210", "patterns": [
        r"\bfuneral\b", r"\bmortuary\b", r"\bcemetery\b", r"\bcremation\b",
        r"\bmemorial park\b",
    ]},
    "waste": {"naics": "562111", "patterns": [
        r"\bwaste\b", r"\bsanitation\b", r"\brecycling\b", r"\brefuse\b",
        r"\bsolid waste\b", r"\btrash\b",
    ]},
    "printing": {"naics": "323111", "patterns": [
        r"\bprinting\b", r"\bpress\b(?!.*asso)", r"\blithograph\b", r"\bprint shop\b",
    ]},
    "dental": {"naics": "621210", "patterns": [
        r"\bdental\b", r"\bdentist\b", r"\bDDS\b", r"\bDMD\b", r"\borthodont\b",
    ]},
    "labor_org": {"naics": "813930", "patterns": [
        r"\blabor org\b", r"\bIBEW\b", r"\bUFCW\b", r"\bSEIU\b", r"\bAFSCME\b",
        r"\bteamster\b", r"\bIAM\b(?=\s)", r"\bUSW\b", r"\bUAW\b", r"\bCWA\b",
        r"\bUNITE HERE\b", r"\bLIUNA\b", r"\bIUOE\b", r"\bIBT\b",
        r"\bAFL.?CIO\b", r"\bworkers union\b", r"\btrades council\b",
    ]},
    "security": {"naics": "561612", "patterns": [
        r"\bsecurity guard\b", r"\bsecurity service\b", r"\bsecurity officer\b",
        r"\bprotective service\b",
    ]},
    "library": {"naics": "519120", "patterns": [
        r"\blibrary\b", r"\blibraries\b",
    ]},
    "museum": {"naics": "712110", "patterns": [
        r"\bmuseum\b", r"\bzoo\b", r"\baquarium\b", r"\bbotanical\b",
    ]},
    "child_care": {"naics": "624410", "patterns": [
        r"\bchild care\b", r"\bchildcare\b", r"\bdaycare\b", r"\bday care\b",
        r"\bpreschool\b", r"\bpre.?school\b", r"\bhead start\b",
    ]},
    "telecom": {"naics": "517311", "patterns": [
        r"\btelecom\b", r"\btelecommunication\b", r"\btelephone\b",
    ]},
    "media": {"naics": "511110", "patterns": [
        r"\bnewspaper\b", r"\bbroadcast\b", r"\bgazette\b", r"\btribune\b",
        r"\bherald\b(?!.*health)", r"\btimes\b(?!.*warner)",
    ]},
    "pharmacy": {"naics": "446110", "patterns": [
        r"\bpharmacy\b", r"\bdrug store\b", r"\bapothecary\b",
    ]},
    "airline": {"naics": "481111", "patterns": [
        r"\bairline[s]?\b", r"\bairway[s]?\b", r"\bair line[s]?\b",
    ]},
    "railroad": {"naics": "482111", "patterns": [
        r"\brailroad\b", r"\brailway\b", r"\brail road\b",
    ]},
}

COMPILED_RULES_R2 = []
for category, cfg in KEYWORD_RULES_R2.items():
    for pattern in cfg["patterns"]:
        COMPILED_RULES_R2.append((category, cfg["naics"], re.compile(pattern, re.IGNORECASE)))


def match_keywords_r2(name: str) -> list[str]:
    """Return list of distinct NAICS codes matched by R2 keyword rules."""
    text = (name or "").strip()
    if not text:
        return []
    codes = set()
    for _cat, naics, pat in COMPILED_RULES_R2:
        if pat.search(text):
            codes.add(naics)
    return sorted(codes)


# ---------------------------------------------------------------------------
# Strategy C: Government Broadening
# ---------------------------------------------------------------------------

# More specific government NAICS where determinable
GOV_PATTERNS = [
    # School / education districts
    (re.compile(r"\bschool dist", re.I), "611110"),
    (re.compile(r"\bboard of education\b", re.I), "611110"),
    (re.compile(r"\bindependent school\b", re.I), "611110"),
    (re.compile(r"\bschool board\b", re.I), "611110"),
    # Fire
    (re.compile(r"\bfire dist", re.I), "922160"),
    (re.compile(r"\bfire dep", re.I), "922160"),
    (re.compile(r"\bfire prot", re.I), "922160"),
    # Police / law enforcement
    (re.compile(r"\bpolice dep", re.I), "922120"),
    (re.compile(r"\bsheriff", re.I), "922120"),
    # Transit authority
    (re.compile(r"\btransit authority\b", re.I), "485113"),
    (re.compile(r"\btransportation authority\b", re.I), "485113"),
    (re.compile(r"\btransit dist", re.I), "485113"),
    # Water / sewer
    (re.compile(r"\bwater dist", re.I), "221310"),
    (re.compile(r"\bwater authority\b", re.I), "221310"),
    (re.compile(r"\bsewer dist", re.I), "221320"),
    (re.compile(r"\bsewer authority\b", re.I), "221320"),
    # Housing authority
    (re.compile(r"\bhousing authority\b", re.I), "925110"),
    # Port authority
    (re.compile(r"\bport authority\b", re.I), "488310"),
    # Park district
    (re.compile(r"\bpark dist", re.I), "712190"),
    (re.compile(r"\bpark and rec", re.I), "712190"),
    # General government catch-alls (broad 921190)
    (re.compile(r"\bcounty\b", re.I), "921190"),
    (re.compile(r"\bdistrict\b", re.I), "921190"),
    (re.compile(r"\bauthority\b", re.I), "921190"),
    (re.compile(r"\bdepartment of\b", re.I), "921190"),
    (re.compile(r"\bboard of\b", re.I), "921190"),
    (re.compile(r"\bcommission\b", re.I), "921190"),
    (re.compile(r"\bmunicip", re.I), "921190"),
    (re.compile(r"\bborough\b", re.I), "921190"),
    (re.compile(r"\btownship\b", re.I), "921190"),
    (re.compile(r"\bvillage of\b", re.I), "921190"),
    (re.compile(r"\bcity of\b", re.I), "921190"),
    (re.compile(r"\btown of\b", re.I), "921190"),
    (re.compile(r"\bstate of\b", re.I), "921190"),
]


def match_government(name: str) -> str | None:
    """Return most specific government NAICS, or None."""
    text = (name or "").strip()
    if not text:
        return None
    # Try specific patterns first; they come before catch-alls in the list
    for pat, naics in GOV_PATTERNS:
        if pat.search(text):
            return naics
    return None


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Infer NAICS round 2 (brand + keyword + government)")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode (default if --commit omitted)")
    parser.add_argument("--commit", action="store_true", help="Persist updates")
    args = parser.parse_args()

    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT employer_id, employer_name
            FROM f7_employers_deduped
            WHERE naics IS NULL
        """)
        rows = cur.fetchall()

        updates = []  # (naics, source, employer_id)
        ambiguous = 0
        ambiguous_examples = []
        by_strategy = Counter()
        by_code = Counter()

        for employer_id, employer_name in rows:
            # Strategy A: Brand
            brand_naics = match_brand(employer_name)
            if brand_naics:
                updates.append((brand_naics, "BRAND_INFERRED", employer_id))
                by_strategy["BRAND_INFERRED"] += 1
                by_code[brand_naics] += 1
                continue

            # Strategy B: Extended Keywords
            kw_codes = match_keywords_r2(employer_name)
            if len(kw_codes) == 1:
                updates.append((kw_codes[0], "KEYWORD_INFERRED_R2", employer_id))
                by_strategy["KEYWORD_INFERRED_R2"] += 1
                by_code[kw_codes[0]] += 1
                continue
            elif len(kw_codes) > 1:
                ambiguous += 1
                if len(ambiguous_examples) < 15:
                    ambiguous_examples.append((employer_name, kw_codes))
                continue

            # Strategy C: Government
            gov_naics = match_government(employer_name)
            if gov_naics:
                updates.append((gov_naics, "GOV_INFERRED", employer_id))
                by_strategy["GOV_INFERRED"] += 1
                by_code[gov_naics] += 1
                continue

        no_match = len(rows) - len(updates) - ambiguous

        print(f"NULL NAICS rows scanned: {len(rows):,}")
        print(f"Total matches: {len(updates):,}")
        print(f"Ambiguous (skipped): {ambiguous:,}")
        print(f"No match: {no_match:,}")
        print()

        print("Matches by strategy:")
        for strat, cnt in sorted(by_strategy.items(), key=lambda x: x[1], reverse=True):
            print(f"  {strat}: {cnt:,}")
        print()

        print("Matches by NAICS code (top 30):")
        for naics, cnt in sorted(by_code.items(), key=lambda x: x[1], reverse=True)[:30]:
            print(f"  {naics}: {cnt:,}")
        print()

        if ambiguous_examples:
            print("Sample ambiguous rows:")
            for name, codes in ambiguous_examples:
                print(f"  {name} -> {', '.join(codes)}")
            print()

        # Apply updates
        updated = 0
        for naics_code, source, employer_id in updates:
            cur.execute(
                """
                UPDATE f7_employers_deduped
                SET naics = %s,
                    naics_source = %s
                WHERE employer_id = %s
                  AND naics IS NULL
                """,
                (naics_code, source, employer_id),
            )
            updated += cur.rowcount

        print(f"Rows updated in transaction: {updated:,}")

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
