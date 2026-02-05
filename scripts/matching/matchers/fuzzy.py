"""
Fuzzy matching implementation (Tier 5).

Uses PostgreSQL pg_trgm extension for trigram-based fuzzy matching.
"""

from typing import Optional, List, Dict, Any
from .base import BaseMatcher, MatchResult
from ..config import TIER_FUZZY, DEFAULT_FUZZY_THRESHOLD
from ..normalizer import normalize_employer_name


class TrigramMatcher(BaseMatcher):
    """
    Tier 4: Fuzzy trigram matching using pg_trgm.

    Uses PostgreSQL's pg_trgm extension for similarity matching.
    Falls back to Python difflib if pg_trgm is unavailable.
    """

    def __init__(self, conn, config, threshold: float = None):
        super().__init__(conn, config)
        self.tier = TIER_FUZZY
        self.method = "FUZZY"
        self.threshold = threshold or config.fuzzy_threshold or DEFAULT_FUZZY_THRESHOLD
        self._pg_trgm_available = None

    def _check_pg_trgm(self) -> bool:
        """Check if pg_trgm extension is available."""
        if self._pg_trgm_available is None:
            cursor = self.conn.cursor()
            try:
                cursor.execute("SELECT 'test' % 'test'")
                self._pg_trgm_available = True
            except Exception:
                self._pg_trgm_available = False
                self.conn.rollback()
        return self._pg_trgm_available

    def match(self, source_id: Any, source_name: str,
              state: Optional[str] = None,
              city: Optional[str] = None,
              ein: Optional[str] = None,
              address: Optional[str] = None) -> Optional[MatchResult]:
        """Match by fuzzy trigram similarity."""
        if not source_name:
            return None

        normalized = normalize_employer_name(source_name, "fuzzy")
        if len(normalized) < 4:  # Trigrams need at least 3 chars
            return None

        cfg = self.config

        if self._check_pg_trgm():
            return self._match_with_pg_trgm(source_id, source_name, normalized, state)
        else:
            return self._match_with_difflib(source_id, source_name, normalized, state)

    def _match_with_pg_trgm(self, source_id: Any, source_name: str,
                            normalized: str, state: Optional[str]) -> Optional[MatchResult]:
        """Match using PostgreSQL pg_trgm."""
        cfg = self.config
        cursor = self.conn.cursor()

        # Use normalized column if available, otherwise normalize inline
        if cfg.target_normalized_col:
            name_col = cfg.target_normalized_col
        else:
            name_col = f"""
                LOWER(TRIM(REGEXP_REPLACE(
                    REGEXP_REPLACE({cfg.target_name_col},
                        E'\\\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company)\\\\b\\\\.?', '', 'gi'),
                    E'[^\\\\w\\\\s]', ' ', 'g'
                )))
            """

        # Use named parameters to avoid issues with % operator in pg_trgm
        query = f"""
            SELECT
                {cfg.target_id_col},
                {cfg.target_name_col},
                similarity({name_col}, %(term)s) as sim
            FROM {cfg.target_table}
            WHERE similarity({name_col}, %(term)s) >= %(threshold)s
        """
        params = {"term": normalized, "threshold": self.threshold}

        # State filter
        if cfg.require_state_match and state and cfg.target_state_col:
            query += f" AND UPPER({cfg.target_state_col}) = UPPER(%(state)s)"
            params["state"] = state

        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        query += f"""
            ORDER BY sim DESC
            LIMIT 1
        """

        try:
            cursor.execute(query, params)
            row = cursor.fetchone()

            if row:
                target_id, target_name, similarity = row
                return self._create_result(
                    source_id=source_id,
                    source_name=source_name,
                    target_id=target_id,
                    target_name=target_name,
                    score=float(similarity),
                    metadata={
                        "normalized": normalized,
                        "similarity": round(float(similarity), 4),
                        "state": state,
                        "method": "pg_trgm"
                    }
                )
        except Exception as e:
            self.conn.rollback()
            raise

        return None

    def _match_with_difflib(self, source_id: Any, source_name: str,
                            normalized: str, state: Optional[str]) -> Optional[MatchResult]:
        """Fallback matching using Python difflib."""
        from difflib import SequenceMatcher

        cfg = self.config
        cursor = self.conn.cursor()

        # Fetch candidates
        query = f"""
            SELECT {cfg.target_id_col}, {cfg.target_name_col}
            FROM {cfg.target_table}
            WHERE 1=1
        """
        params = []

        if cfg.require_state_match and state and cfg.target_state_col:
            query += f" AND UPPER({cfg.target_state_col}) = UPPER(%s)"
            params.append(state)

        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        # Limit candidates to prevent memory issues
        query += " LIMIT 10000"

        cursor.execute(query, params)

        best_match = None
        best_score = 0.0

        for row in cursor.fetchall():
            target_id, target_name = row
            target_normalized = normalize_employer_name(target_name, "fuzzy")

            if len(target_normalized) < 4:
                continue

            score = SequenceMatcher(None, normalized, target_normalized).ratio()

            if score > best_score and score >= self.threshold:
                best_score = score
                best_match = (target_id, target_name)

        if best_match:
            return self._create_result(
                source_id=source_id,
                source_name=source_name,
                target_id=best_match[0],
                target_name=best_match[1],
                score=best_score,
                metadata={
                    "normalized": normalized,
                    "similarity": round(best_score, 4),
                    "state": state,
                    "method": "difflib"
                }
            )

        return None

    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """Batch fuzzy matching."""
        results = []
        cfg = self.config

        if self._check_pg_trgm():
            # With pg_trgm, we can do efficient batch queries
            return self._batch_match_pg_trgm(source_records)
        else:
            # Without pg_trgm, process one at a time
            for r in source_records:
                result = self.match(
                    source_id=r.get(cfg.source_id_col),
                    source_name=r.get(cfg.source_name_col),
                    state=r.get(cfg.source_state_col),
                    city=r.get(cfg.source_city_col),
                )
                if result:
                    results.append(result)

        return results

    def _batch_match_pg_trgm(self, source_records: List[Dict]) -> List[MatchResult]:
        """Batch fuzzy matching with pg_trgm."""
        results = []
        cfg = self.config
        cursor = self.conn.cursor()

        # Group by state for efficient querying
        by_state: Dict[str, List[Dict]] = {}
        for r in source_records:
            state = r.get(cfg.source_state_col, "") if cfg.require_state_match else ""
            if state not in by_state:
                by_state[state] = []
            by_state[state].append(r)

        # Use normalized column if available
        if cfg.target_normalized_col:
            name_col = cfg.target_normalized_col
        else:
            name_col = f"""
                LOWER(TRIM(REGEXP_REPLACE(
                    REGEXP_REPLACE({cfg.target_name_col},
                        E'\\\\b(inc|incorporated|corp|corporation|llc|llp|ltd|limited|co|company)\\\\b\\\\.?', '', 'gi'),
                    E'[^\\\\w\\\\s]', ' ', 'g'
                )))
            """

        for state, records in by_state.items():
            for r in records:
                name = r.get(cfg.source_name_col)
                if not name:
                    continue

                normalized = normalize_employer_name(name, "fuzzy")
                if len(normalized) < 4:
                    continue

                # Use named parameters to avoid issues with % operator
                query = f"""
                    SELECT
                        {cfg.target_id_col},
                        {cfg.target_name_col},
                        similarity({name_col}, %(term)s) as sim
                    FROM {cfg.target_table}
                    WHERE similarity({name_col}, %(term)s) >= %(threshold)s
                """
                params = {"term": normalized, "threshold": self.threshold}

                if state and cfg.target_state_col:
                    query += f" AND UPPER({cfg.target_state_col}) = UPPER(%(state)s)"
                    params["state"] = state

                if cfg.target_filter:
                    query += f" AND ({cfg.target_filter})"

                query += f"""
                    ORDER BY sim DESC
                    LIMIT 1
                """

                cursor.execute(query, params)
                row = cursor.fetchone()

                if row:
                    target_id, target_name, similarity = row
                    results.append(self._create_result(
                        source_id=r.get(cfg.source_id_col),
                        source_name=name,
                        target_id=target_id,
                        target_name=target_name,
                        score=float(similarity),
                        metadata={
                            "normalized": normalized,
                            "similarity": round(float(similarity), 4),
                            "method": "pg_trgm"
                        }
                    ))

        return results
