"""
Address-based matcher.

Matches on normalized name + normalized address + city + state.
This is Tier 3 (between Normalized and Aggressive).
"""

import re
from typing import Optional, List, Dict, Any

from .base import BaseMatcher, MatchResult
from ..config import TIER_ADDRESS


def extract_street_number(address: str) -> str:
    """
    Extract the street number from an address.

    Handles messy NLRB format like "City, ST ZIPCODE, 123 Main Street"
    Returns the building number, not the ZIP code.
    """
    if not address:
        return ""

    # First, try to skip past any "City, ST ZIP," prefix
    # NLRB format: "Fort Wayne, IN 46801, 110 E Wayne Street"
    # We want to extract 110, not 46801

    # Remove ZIP codes (5 or 5+4 digit patterns)
    clean_addr = re.sub(r'\b\d{5}(-\d{4})?\b', '', address)

    # Remove state abbreviations
    clean_addr = re.sub(r'\b[A-Z]{2}\b', '', clean_addr)

    # Remove city name prefix (text before comma)
    clean_addr = re.sub(r'^[^,]+,\s*', '', clean_addr)

    # Now find first number sequence - should be street number
    match = re.search(r'\b(\d+)\b', clean_addr)
    if match:
        return match.group(1)

    # Fallback: try original address but look for number followed by word (street name)
    # This catches "123 Main St" patterns
    match = re.search(r'\b(\d+)\s+[A-Za-z]', address)
    return match.group(1) if match else ""


def normalize_address(address: str) -> str:
    """
    Normalize a street address for matching.

    - Lowercase
    - Expand common abbreviations
    - Remove punctuation
    - Normalize whitespace
    - Extract street portion (tries to ignore city/state/zip at end)
    """
    if not address:
        return ""

    addr = address.lower().strip()

    # Try to extract just the street address portion
    # Remove zip codes (5 or 9 digits)
    addr = re.sub(r'\b\d{5}(-\d{4})?\b', '', addr)

    # Remove state abbreviations at word boundaries
    states = r'\b(al|ak|az|ar|ca|co|ct|de|fl|ga|hi|id|il|in|ia|ks|ky|la|me|md|ma|mi|mn|ms|mo|mt|ne|nv|nh|nj|nm|ny|nc|nd|oh|ok|or|pa|ri|sc|sd|tn|tx|ut|vt|va|wa|wv|wi|wy|dc)\b'
    addr = re.sub(states, '', addr, flags=re.IGNORECASE)

    # Remove common city names that appear before the address (messy NLRB data)
    # Remove text that looks like "City, ST" patterns
    addr = re.sub(r'^[a-z\s]+,\s*', '', addr)

    # Expand common abbreviations
    expansions = {
        r'\bst\b': 'street',
        r'\bave\b': 'avenue',
        r'\bav\b': 'avenue',
        r'\bblvd\b': 'boulevard',
        r'\brd\b': 'road',
        r'\bdr\b': 'drive',
        r'\bln\b': 'lane',
        r'\bct\b': 'court',
        r'\bpl\b': 'place',
        r'\bpkwy\b': 'parkway',
        r'\bhwy\b': 'highway',
        r'\bfl\b': 'floor',
        r'\bste\b': 'suite',
        r'\bapt\b': 'apartment',
        r'\bunit\b': 'unit',
        r'\bn\b': 'north',
        r'\bs\b': 'south',
        r'\be\b': 'east',
        r'\bw\b': 'west',
        r'\bnw\b': 'northwest',
        r'\bne\b': 'northeast',
        r'\bsw\b': 'southwest',
        r'\bse\b': 'southeast',
    }

    for pattern, replacement in expansions.items():
        addr = re.sub(pattern, replacement, addr)

    # Remove punctuation except digits
    addr = re.sub(r'[^\w\s]', ' ', addr)

    # Normalize whitespace
    addr = ' '.join(addr.split())

    return addr


class AddressMatcher(BaseMatcher):
    """
    Matches on fuzzy name + street number + city + state.

    This tier is useful for finding matches where:
    - Company names vary (d/b/a, legal name vs trade name)
    - Company rebranded but kept the same address
    - Different legal entities at the same location

    Uses street number + city + state as a strong location signal,
    combined with trigram name similarity (>=0.4 threshold).
    """

    def __init__(self, conn, config):
        super().__init__(conn, config)
        self.tier = TIER_ADDRESS
        self.method = "ADDRESS"
        self.name_threshold = 0.4  # Lower threshold since address provides confidence

    def match(self, source_id: Any, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None) -> Optional[MatchResult]:
        """
        Match by fuzzy name + street number + city + state.
        """
        cfg = self.config

        # Skip if no address columns configured or no address provided
        if not cfg.source_address_col or not cfg.target_address_col:
            return None
        if not address or not state:
            return None

        # Normalize source values
        from ..normalizer import normalize_employer_name
        normalized_name = normalize_employer_name(source_name, level="standard")
        street_number = extract_street_number(address)

        if not normalized_name or not street_number or len(normalized_name) < 3:
            return None

        cursor = self.conn.cursor()

        # Build query - use fuzzy name match + exact address match
        # The address match provides confidence, so we can use a lower name threshold
        target_name_col = cfg.target_normalized_col or cfg.target_name_col

        query = f"""
            SELECT {cfg.target_id_col}, {cfg.target_name_col}, {cfg.target_address_col},
                   similarity(LOWER({target_name_col}), %(name)s) as sim
            FROM {cfg.target_table}
            WHERE {cfg.target_address_col} ~ %(street_num_pattern)s
              AND UPPER({cfg.target_state_col}) = %(state)s
              AND similarity(LOWER({target_name_col}), %(name)s) >= %(threshold)s
            ORDER BY sim DESC
            LIMIT 1
        """

        params = {
            "name": normalized_name,
            "street_num_pattern": f"^{street_number}[^0-9]",
            "state": state.upper().strip(),
            "threshold": self.name_threshold,
        }

        # Add city filter if available (optional for address matching)
        if city and cfg.target_city_col:
            query = query.replace(
                f"AND UPPER({cfg.target_state_col}) = %(state)s",
                f"AND UPPER({cfg.target_state_col}) = %(state)s AND LOWER({cfg.target_city_col}) = %(city)s"
            )
            params["city"] = city.lower().strip()

        # Add target filter if configured
        if cfg.target_filter:
            query = query.replace("ORDER BY", f"AND {cfg.target_filter} ORDER BY")

        try:
            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                return self._create_result(
                    source_id=source_id,
                    source_name=source_name,
                    target_id=row[0],
                    target_name=row[1],
                    score=row[3],  # similarity score
                    metadata={
                        "street_number": street_number,
                        "target_address": row[2][:30] if row[2] else "",
                        "name_similarity": round(row[3], 3)
                    }
                )
        except Exception as e:
            # Log but don't fail - address matching is optional
            pass

        return None

    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """Match multiple records."""
        results = []
        for record in source_records:
            result = self.match(
                source_id=record.get("id"),
                source_name=record.get("name", ""),
                state=record.get("state"),
                city=record.get("city"),
                address=record.get("address"),
            )
            if result:
                results.append(result)
        return results
