"""
Exact matching implementations (Tier 1, 2, 4).

- EINMatcher: Tier 1 - Exact EIN match
- NormalizedMatcher: Tier 2 - Exact normalized name + city + state
- AggressiveMatcher: Tier 4 - Aggressive normalization + city

Note: Tier 3 (ADDRESS) is in address.py
"""

from typing import Optional, List, Dict, Any
from .base import BaseMatcher, MatchResult
from ..config import TIER_EIN, TIER_NORMALIZED, TIER_AGGRESSIVE
from ..normalizer import normalize_employer_name


class EINMatcher(BaseMatcher):
    """
    Tier 1: Exact EIN matching.

    Highest confidence - EIN is a unique identifier.
    """

    def __init__(self, conn, config):
        super().__init__(conn, config)
        self.tier = TIER_EIN
        self.method = "EIN"

    def match(self, source_id: Any, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None) -> Optional[MatchResult]:
        """Match by exact EIN."""
        if not ein:
            return None

        # Clean EIN (remove dashes)
        ein_clean = ein.replace("-", "").strip()
        if len(ein_clean) != 9 or not ein_clean.isdigit():
            return None

        cfg = self.config
        if not cfg.target_ein_col:
            return None

        cursor = self.conn.cursor()

        query = f"""
            SELECT {cfg.target_id_col}, {cfg.target_name_col}
            FROM {cfg.target_table}
            WHERE REPLACE({cfg.target_ein_col}, '-', '') = %s
        """
        params = [ein_clean]

        # Add state filter if configured
        if cfg.require_state_match and state and cfg.target_state_col:
            query += f" AND UPPER({cfg.target_state_col}) = UPPER(%s)"
            params.append(state)

        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        query += " LIMIT 1"

        cursor.execute(query, params)
        row = cursor.fetchone()

        if row:
            return self._create_result(
                source_id=source_id,
                source_name=source_name,
                target_id=row[0],
                target_name=row[1],
                score=1.0,
                metadata={"ein": ein_clean}
            )

        return None

    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """Batch EIN matching."""
        results = []

        # Filter to records with EIN
        records_with_ein = [r for r in source_records if r.get("ein")]
        if not records_with_ein:
            return results

        cfg = self.config
        if not cfg.target_ein_col:
            return results

        # Build EIN lookup
        ein_to_source = {}
        for r in records_with_ein:
            ein_clean = r["ein"].replace("-", "").strip()
            if len(ein_clean) == 9 and ein_clean.isdigit():
                ein_to_source[ein_clean] = r

        if not ein_to_source:
            return results

        cursor = self.conn.cursor()

        # Batch query
        placeholders = ",".join(["%s"] * len(ein_to_source))
        query = f"""
            SELECT REPLACE({cfg.target_ein_col}, '-', ''), {cfg.target_id_col}, {cfg.target_name_col}
            FROM {cfg.target_table}
            WHERE REPLACE({cfg.target_ein_col}, '-', '') IN ({placeholders})
        """
        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        cursor.execute(query, list(ein_to_source.keys()))

        for row in cursor.fetchall():
            ein, target_id, target_name = row
            if ein in ein_to_source:
                source = ein_to_source[ein]
                results.append(self._create_result(
                    source_id=source[cfg.source_id_col],
                    source_name=source[cfg.source_name_col],
                    target_id=target_id,
                    target_name=target_name,
                    score=1.0,
                    metadata={"ein": ein}
                ))

        return results


class NormalizedMatcher(BaseMatcher):
    """
    Tier 2: Normalized name + city + state matching.

    Uses standard normalization for exact matching.
    """

    def __init__(self, conn, config):
        super().__init__(conn, config)
        self.tier = TIER_NORMALIZED
        self.method = "NORMALIZED"

    def match(self, source_id: Any, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None) -> Optional[MatchResult]:
        """Match by normalized name + location.

        Fetches all candidates (up to 20) and disambiguates by city when
        multiple targets share the same normalized name.  Returns None for
        truly ambiguous cases so that a later tier can try with more info.
        """
        if not source_name:
            return None

        normalized = normalize_employer_name(source_name, "standard")
        if len(normalized) < 3:
            return None

        cfg = self.config
        cursor = self.conn.cursor()

        # Build query
        if cfg.target_normalized_col:
            name_condition = f"LOWER({cfg.target_normalized_col}) = %s"
        else:
            # Use inline normalization
            name_condition = f"""
                LOWER(TRIM(REGEXP_REPLACE(
                    REGEXP_REPLACE({cfg.target_name_col},
                        E'\\\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company)\\\\b\\\\.?', '', 'gi'),
                    E'[^\\\\w\\\\s]', ' ', 'g'
                ))) = %s
            """

        # Select city column for disambiguation when available
        select_cols = f"{cfg.target_id_col}, {cfg.target_name_col}"
        if cfg.target_city_col:
            select_cols += f", {cfg.target_city_col}"

        query = f"""
            SELECT {select_cols}
            FROM {cfg.target_table}
            WHERE {name_condition}
        """
        params = [normalized.lower()]

        # Add state filter
        if cfg.require_state_match and state and cfg.target_state_col:
            query += f" AND UPPER({cfg.target_state_col}) = UPPER(%s)"
            params.append(state)

        # Add city filter if strict
        if cfg.require_city_match and city and cfg.target_city_col:
            query += f" AND UPPER({cfg.target_city_col}) = UPPER(%s)"
            params.append(city)

        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        query += " LIMIT 20"

        cursor.execute(query, params)
        rows = cursor.fetchall()

        if not rows:
            return None

        # Single candidate — return directly
        if len(rows) == 1:
            return self._create_result(
                source_id=source_id,
                source_name=source_name,
                target_id=rows[0][0],
                target_name=rows[0][1],
                score=1.0,
                metadata={"normalized": normalized, "state": state, "city": city}
            )

        # Multiple candidates — try city disambiguation
        if city and cfg.target_city_col:
            city_upper = city.upper().strip()
            city_matches = [r for r in rows
                            if r[2] and r[2].upper().strip() == city_upper]
            if len(city_matches) == 1:
                return self._create_result(
                    source_id=source_id,
                    source_name=source_name,
                    target_id=city_matches[0][0],
                    target_name=city_matches[0][1],
                    score=1.0,
                    metadata={
                        "normalized": normalized, "state": state, "city": city,
                        "disambiguated_by": "city",
                        "candidates": len(rows),
                    }
                )

        # Cannot disambiguate — skip so a later tier can try with more info
        return None

    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """Batch normalized matching with city disambiguation."""
        results = []
        cfg = self.config
        cursor = self.conn.cursor()

        # Build normalized lookup
        normalized_to_sources = {}
        for r in source_records:
            name = r.get(cfg.source_name_col)
            if name:
                normalized = normalize_employer_name(name, "standard")
                if len(normalized) >= 3:
                    key = (
                        normalized,
                        r.get(cfg.source_state_col, "").upper() if cfg.require_state_match else "",
                    )
                    if key not in normalized_to_sources:
                        normalized_to_sources[key] = []
                    normalized_to_sources[key].append(r)

        if not normalized_to_sources:
            return results

        # Query in batches
        for (normalized, state), sources in normalized_to_sources.items():
            if cfg.target_normalized_col:
                name_condition = f"LOWER({cfg.target_normalized_col}) = %s"
            else:
                name_condition = f"""
                    LOWER(TRIM(REGEXP_REPLACE(
                        REGEXP_REPLACE({cfg.target_name_col},
                            E'\\\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company)\\\\b\\\\.?', '', 'gi'),
                        E'[^\\\\w\\\\s]', ' ', 'g'
                    ))) = %s
                """

            # Select city for disambiguation
            select_cols = f"{cfg.target_id_col}, {cfg.target_name_col}"
            if cfg.target_city_col:
                select_cols += f", {cfg.target_city_col}"

            query = f"""
                SELECT {select_cols}
                FROM {cfg.target_table}
                WHERE {name_condition}
            """
            params = [normalized.lower()]

            if state and cfg.target_state_col:
                query += f" AND UPPER({cfg.target_state_col}) = UPPER(%s)"
                params.append(state)

            if cfg.target_filter:
                query += f" AND ({cfg.target_filter})"

            query += " LIMIT 20"

            cursor.execute(query, params)
            rows = cursor.fetchall()

            if not rows:
                continue

            if len(rows) == 1:
                # Single target — match all sources to it
                for source in sources:
                    results.append(self._create_result(
                        source_id=source[cfg.source_id_col],
                        source_name=source[cfg.source_name_col],
                        target_id=rows[0][0],
                        target_name=rows[0][1],
                        score=1.0,
                        metadata={"normalized": normalized}
                    ))
            else:
                # Multiple targets — disambiguate per source record by city
                for source in sources:
                    src_city = (source.get(cfg.source_city_col) or "").upper().strip() if cfg.source_city_col else ""
                    if src_city and cfg.target_city_col:
                        city_matches = [r for r in rows
                                        if r[2] and r[2].upper().strip() == src_city]
                        if len(city_matches) == 1:
                            results.append(self._create_result(
                                source_id=source[cfg.source_id_col],
                                source_name=source[cfg.source_name_col],
                                target_id=city_matches[0][0],
                                target_name=city_matches[0][1],
                                score=1.0,
                                metadata={
                                    "normalized": normalized,
                                    "disambiguated_by": "city",
                                    "candidates": len(rows),
                                }
                            ))
                            continue
                    # Cannot disambiguate — skip this source record

        return results


class AggressiveMatcher(BaseMatcher):
    """
    Tier 3: Aggressive normalization matching.

    Expands abbreviations, removes stopwords, and matches with city.
    """

    def __init__(self, conn, config):
        super().__init__(conn, config)
        self.tier = TIER_AGGRESSIVE
        self.method = "AGGRESSIVE"

    def match(self, source_id: Any, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None) -> Optional[MatchResult]:
        """Match by aggressively normalized name.

        Collects ALL matching candidates and disambiguates instead of
        returning the first hit.  Returns None for ambiguous cases so
        that a later tier (fuzzy) can try with more info.
        """
        if not source_name:
            return None

        normalized = normalize_employer_name(source_name, "aggressive")
        if len(normalized) < 3:
            return None

        cfg = self.config
        cursor = self.conn.cursor()

        # For aggressive matching, we query all potential matches
        # and compare normalized forms.  Also select city for disambiguation.
        select_cols = f"{cfg.target_id_col}, {cfg.target_name_col}"
        if cfg.target_city_col:
            select_cols += f", {cfg.target_city_col}"

        query = f"""
            SELECT {select_cols}
            FROM {cfg.target_table}
            WHERE 1=1
        """
        params = []

        # State filter (required for aggressive)
        if state and cfg.target_state_col:
            query += f" AND UPPER({cfg.target_state_col}) = UPPER(%s)"
            params.append(state)

        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        # Use trigram to narrow candidates if available
        if cfg.target_normalized_col:
            query += f"""
                AND {cfg.target_normalized_col} %% %s
            """
            params.append(normalized)

        query += " LIMIT 100"

        try:
            cursor.execute(query, params)
        except Exception:
            # Trigram extension might not be available
            # Fall back without trigram filter
            self.conn.rollback()
            query = f"""
                SELECT {select_cols}
                FROM {cfg.target_table}
                WHERE 1=1
            """
            params = []
            if state and cfg.target_state_col:
                query += f" AND UPPER({cfg.target_state_col}) = UPPER(%s)"
                params.append(state)
            if cfg.target_filter:
                query += f" AND ({cfg.target_filter})"
            query += " LIMIT 500"
            cursor.execute(query, params)

        # Collect ALL aggressive-normalized matches
        matches = []
        for row in cursor.fetchall():
            target_id, target_name = row[0], row[1]
            target_city = row[2] if len(row) > 2 else None
            target_normalized = normalize_employer_name(target_name, "aggressive")

            if normalized == target_normalized:
                matches.append((target_id, target_name, target_city))

        if not matches:
            return None

        # Single match — return directly
        if len(matches) == 1:
            return self._create_result(
                source_id=source_id,
                source_name=source_name,
                target_id=matches[0][0],
                target_name=matches[0][1],
                score=0.95,
                metadata={
                    "normalized": normalized,
                    "target_normalized": normalized,
                    "city": city,
                }
            )

        # Multiple matches — disambiguate by city
        if city and cfg.target_city_col:
            city_upper = city.upper().strip()
            city_matches = [m for m in matches
                            if m[2] and m[2].upper().strip() == city_upper]
            if len(city_matches) == 1:
                return self._create_result(
                    source_id=source_id,
                    source_name=source_name,
                    target_id=city_matches[0][0],
                    target_name=city_matches[0][1],
                    score=0.95,
                    metadata={
                        "normalized": normalized,
                        "target_normalized": normalized,
                        "city": city,
                        "disambiguated_by": "city",
                        "candidates": len(matches),
                    }
                )

        # Cannot disambiguate — skip so fuzzy tier can try
        return None

    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """Batch aggressive matching."""
        results = []

        # Process records one at a time for aggressive matching
        # (batch optimization is complex due to city requirement)
        for r in source_records:
            cfg = self.config
            result = self.match(
                source_id=r.get(cfg.source_id_col),
                source_name=r.get(cfg.source_name_col),
                state=r.get(cfg.source_state_col),
                city=r.get(cfg.source_city_col),
                ein=r.get(cfg.source_ein_col) if cfg.source_ein_col else None,
            )
            if result:
                results.append(result)

        return results
