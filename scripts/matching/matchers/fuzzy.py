"""
Fuzzy matching implementation (Tier 5).

Uses PostgreSQL pg_trgm extension for trigram-based candidate retrieval,
with RapidFuzz composite scoring for final match selection.
Falls back to RapidFuzz-only matching if pg_trgm is unavailable.
"""

from typing import Optional, List, Dict, Any
from .base import BaseMatcher, MatchResult
from ..config import TIER_FUZZY, DEFAULT_FUZZY_THRESHOLD
from ..normalizer import normalize_employer_name

try:
    from rapidfuzz import fuzz
    from rapidfuzz.distance import JaroWinkler
    from rapidfuzz import process as rf_process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


def _composite_score(source: str, target: str) -> float:
    """
    Compute a composite similarity score using multiple RapidFuzz algorithms.

    Weights:
      0.35 × Jaro-Winkler  (good for transposed chars, prefix emphasis)
      0.35 × token_set_ratio (handles word reordering, subset matching)
      0.30 × fuzz.ratio (standard Levenshtein-based)

    Returns float 0.0-1.0.
    """
    if not HAS_RAPIDFUZZ:
        from difflib import SequenceMatcher
        return SequenceMatcher(None, source, target).ratio()

    jw = JaroWinkler.similarity(source, target)
    tsr = fuzz.token_set_ratio(source, target) / 100.0
    ratio = fuzz.ratio(source, target) / 100.0
    return 0.35 * jw + 0.35 * tsr + 0.30 * ratio


class TrigramMatcher(BaseMatcher):
    """
    Tier 5: Fuzzy matching using pg_trgm candidate retrieval + RapidFuzz re-scoring.

    Workflow:
    1. pg_trgm retrieves top-5 candidates above a lower threshold
    2. RapidFuzz composite score re-ranks candidates
    3. Best composite score above the final threshold is returned

    Falls back to RapidFuzz batch matching if pg_trgm is unavailable.
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
        """Match by fuzzy similarity."""
        if not source_name:
            return None

        normalized = normalize_employer_name(source_name, "fuzzy")
        if len(normalized) < 4:  # Trigrams need at least 3 chars
            return None

        if self._check_pg_trgm():
            return self._match_with_pg_trgm(source_id, source_name, normalized, state)
        else:
            return self._match_with_rapidfuzz(source_id, source_name, normalized, state)

    def _match_with_pg_trgm(self, source_id: Any, source_name: str,
                            normalized: str, state: Optional[str]) -> Optional[MatchResult]:
        """
        Hybrid matching: pg_trgm for candidate retrieval, RapidFuzz for re-scoring.

        Fetches top 5 candidates from PostgreSQL, then picks the best
        composite score above threshold.
        """
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

        # Use a lower pg_trgm threshold for candidate retrieval (cast wider net)
        retrieval_threshold = max(self.threshold - 0.15, 0.3)

        query = f"""
            SELECT
                {cfg.target_id_col},
                {cfg.target_name_col},
                {name_col} as target_normalized,
                similarity({name_col}, %(term)s) as sim
            FROM {cfg.target_table}
            WHERE similarity({name_col}, %(term)s) >= %(threshold)s
        """
        params = {"term": normalized, "threshold": retrieval_threshold}

        # State filter
        if cfg.require_state_match and state and cfg.target_state_col:
            query += f" AND UPPER({cfg.target_state_col}) = UPPER(%(state)s)"
            params["state"] = state

        if cfg.target_filter:
            query += f" AND ({cfg.target_filter})"

        query += """
            ORDER BY sim DESC
            LIMIT 5
        """

        try:
            cursor.execute(query, params)
            candidates = cursor.fetchall()

            if not candidates:
                return None

            # Re-score with RapidFuzz composite
            best_result = None
            best_composite = 0.0

            for target_id, target_name, target_norm, pg_sim in candidates:
                if not target_norm:
                    target_norm = normalize_employer_name(target_name, "fuzzy")

                composite = _composite_score(normalized, target_norm)

                if composite > best_composite and composite >= self.threshold:
                    best_composite = composite
                    best_result = (target_id, target_name, target_norm, pg_sim, composite)

            if best_result:
                target_id, target_name, target_norm, pg_sim, composite = best_result
                method = "pg_trgm+rapidfuzz" if HAS_RAPIDFUZZ else "pg_trgm+difflib"
                return self._create_result(
                    source_id=source_id,
                    source_name=source_name,
                    target_id=target_id,
                    target_name=target_name,
                    score=float(composite),
                    metadata={
                        "normalized": normalized,
                        "pg_trgm_similarity": round(float(pg_sim), 4),
                        "composite_score": round(float(composite), 4),
                        "state": state,
                        "method": method,
                        "candidates_evaluated": len(candidates),
                    }
                )
        except Exception as e:
            self.conn.rollback()
            raise

        return None

    def _match_with_rapidfuzz(self, source_id: Any, source_name: str,
                              normalized: str, state: Optional[str]) -> Optional[MatchResult]:
        """Fallback matching using RapidFuzz (no pg_trgm available)."""
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
        rows = cursor.fetchall()

        if not rows:
            return None

        # Build lookup for RapidFuzz batch processing
        best_match = None
        best_score = 0.0

        if HAS_RAPIDFUZZ:
            # Build target dict for fast lookup
            targets = {}
            for target_id, target_name in rows:
                target_norm = normalize_employer_name(target_name, "fuzzy")
                if len(target_norm) >= 4:
                    targets[target_id] = (target_name, target_norm)

            if not targets:
                return None

            # Use RapidFuzz process.extractOne for fast nearest-neighbor
            choices = {tid: tn for tid, (_, tn) in targets.items()}
            result = rf_process.extractOne(
                normalized, choices,
                scorer=fuzz.token_set_ratio,
                score_cutoff=self.threshold * 100
            )

            if result:
                match_norm, raw_score, matched_id = result
                # Re-score with full composite
                target_name, target_norm = targets[matched_id]
                composite = _composite_score(normalized, target_norm)

                if composite >= self.threshold:
                    best_match = (matched_id, target_name)
                    best_score = composite
        else:
            # Pure difflib fallback (slowest path)
            from difflib import SequenceMatcher
            for target_id, target_name in rows:
                target_norm = normalize_employer_name(target_name, "fuzzy")
                if len(target_norm) < 4:
                    continue
                score = SequenceMatcher(None, normalized, target_norm).ratio()
                if score > best_score and score >= self.threshold:
                    best_score = score
                    best_match = (target_id, target_name)

        if best_match:
            method = "rapidfuzz" if HAS_RAPIDFUZZ else "difflib"
            return self._create_result(
                source_id=source_id,
                source_name=source_name,
                target_id=best_match[0],
                target_name=best_match[1],
                score=best_score,
                metadata={
                    "normalized": normalized,
                    "composite_score": round(best_score, 4),
                    "state": state,
                    "method": method,
                }
            )

        return None

    def batch_match(self, source_records: List[Dict]) -> List[MatchResult]:
        """Batch fuzzy matching."""
        results = []
        cfg = self.config

        if self._check_pg_trgm():
            return self._batch_match_pg_trgm(source_records)
        else:
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
        """Batch fuzzy matching with pg_trgm + RapidFuzz re-scoring."""
        results = []
        cfg = self.config

        for r in source_records:
            name = r.get(cfg.source_name_col)
            if not name:
                continue

            normalized = normalize_employer_name(name, "fuzzy")
            if len(normalized) < 4:
                continue

            state = r.get(cfg.source_state_col) if cfg.require_state_match else None

            result = self._match_with_pg_trgm(
                source_id=r.get(cfg.source_id_col),
                source_name=name,
                normalized=normalized,
                state=state,
            )
            if result:
                results.append(result)

        return results
