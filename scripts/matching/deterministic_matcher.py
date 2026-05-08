"""
Deterministic Matching Engine v4 (best-match-wins).

Single entry point for cascade matching against f7_employers_deduped.
Uses in-memory indexes for tiers 1-4 (O(1) lookups) and batched SQL
for tier 5 (fuzzy trigram).

Key improvements over v3:
  - Multi-value indexes: collisions tracked, not silently dropped
  - Best-match-wins: all tiers evaluated, highest-specificity match returned
  - City disambiguation: 83% of name+state collisions resolved by city match
  - Splink disambiguation: unresolved collisions scored by multi-field model

Cascade tiers (evaluated most-specific to least-specific):
  1. EIN exact match (confidence 1.0)
  2. name_standard + city + state (confidence 0.95)
  3. name_standard + state (confidence 0.90)
  4. name_aggressive + state (confidence 0.75)
  5a. RapidFuzz blocked matching (token_sort_ratio >= 0.80)
  5b. Trigram fuzzy fallback (name similarity >= 0.4)

Collision resolution order:
  - Single candidate: accept directly
  - City match narrows to 1: accept with CITY_RESOLVED suffix
  - Splink disambiguation: compare source against 2-10 candidates, pick winner
  - Still ambiguous: flag as AMBIGUOUS with LOW confidence

All matches are logged to unified_match_log.
"""
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
)

# Optional phonetic encoding
try:
    import jellyfish
    HAS_JELLYFISH = True
except ImportError:
    HAS_JELLYFISH = False

# Tier specificity ranking (higher = more specific = preferred)
TIER_RANK = {
    "EIN_EXACT": 100,
    "NAME_CITY_STATE_EXACT": 90,
    "NAME_ZIP_STATE": 85,
    "NAME_STATE_EXACT": 80,
    "NAME_AGGRESSIVE_STATE": 60,
    # New deterministic tiers (v5)
    "SORTED_TOKEN_STATE": 57,
    "COLLAPSED_SPACING_STATE": 55,
    "TRUNCATED_NAME_STATE": 54,
    "STRIPPED_LEADING_NUMS_STATE": 53,
    "STEMMED_NAME_STATE": 52,
    "PHONETIC_STATE": 50,
    # Fuzzy tiers
    "FUZZY_INMEMORY_TRIGRAM": 45,
    "FUZZY_SPLINK_ADAPTIVE": 45,
    "FUZZY_TRIGRAM": 40,
}

# ---------------------------------------------------------------------------
# Helper functions for new deterministic tiers
# ---------------------------------------------------------------------------

_STEM_RULES = [
    ("ations", "at"),
    ("ation", "at"),
    ("tions", "t"),
    ("tion", "t"),
    ("ments", ""),
    ("ment", ""),
    ("ings", ""),
    ("ing", ""),
    ("ies", "y"),
    ("ers", ""),
    ("ors", ""),
    ("es", ""),
    ("s", ""),
]


def _stem_name(name: str) -> str:
    """Simple suffix stemmer for employer names. Deterministic, no NLP."""
    words = name.split()
    stemmed = []
    for w in words:
        if len(w) <= 3:
            stemmed.append(w)
            continue
        for suffix, replacement in _STEM_RULES:
            if w.endswith(suffix) and len(w) - len(suffix) + len(replacement) >= 3:
                w = w[: -len(suffix)] + replacement
                break
        stemmed.append(w)
    return " ".join(stemmed)


def _phonetic_key(name: str) -> str:
    """Generate phonetic key from first 3 significant words using Metaphone."""
    if not HAS_JELLYFISH:
        return ""
    words = name.split()[:4]
    codes = []
    for w in words:
        if len(w) < 2:
            continue
        codes.append(jellyfish.metaphone(w))
    return "|".join(codes) if codes else ""


def _char_trigrams(s: str) -> set:
    """Extract character trigrams from a string."""
    if len(s) < 3:
        return set()
    return {s[i : i + 3] for i in range(len(s) - 2)}


def _jaccard_bigrams(s1: str, s2: str) -> float:
    """Character bigram Jaccard similarity for phonetic validation."""
    if len(s1) < 2 or len(s2) < 2:
        return 0.0
    bg1 = {s1[i : i + 2] for i in range(len(s1) - 1)}
    bg2 = {s2[i : i + 2] for i in range(len(s2) - 1)}
    if not bg1 or not bg2:
        return 0.0
    return len(bg1 & bg2) / len(bg1 | bg2)


class DeterministicMatcher:
    """Cascade deterministic matcher with best-match-wins logic."""
    HIGH_THRESHOLD = 0.85
    MEDIUM_THRESHOLD = 0.70
    DEFAULT_MIN_NAME_SIM = 0.90

    def __init__(self, conn, run_id: str, source_system: str,
                 dry_run: bool = False, skip_fuzzy: bool = False):
        self.conn = conn
        self.run_id = run_id
        self.source_system = source_system
        self.dry_run = dry_run
        self.skip_fuzzy = skip_fuzzy
        self.stats = {
            "total": 0, "matched": 0,
            "by_method": {}, "by_band": {"HIGH": 0, "MEDIUM": 0, "LOW": 0},
            "collisions_resolved": 0,
            "collisions_ambiguous": 0,
        }
        self.min_name_similarity = self._load_min_name_similarity()
        self._log_buffer = []
        self._indexes_loaded = False

        # In-memory indexes: each key maps to LIST of (employer_id, employer_name, city)
        self._ein_idx = {}              # ein -> (employer_id, employer_name)
        self._name_state_idx = {}       # (name_standard, STATE) -> [(eid, ename, CITY), ...]
        self._name_city_state_idx = {}  # (name_standard, CITY, STATE) -> [(eid, ename), ...]
        self._name_zip_state_idx = {}   # (name_standard, ZIP5, STATE) -> [(eid, ename, CITY), ...]
        self._agg_state_idx = {}        # (name_aggressive, STATE) -> [(eid, ename, CITY), ...]

        # New v5 deterministic tier indexes
        self._sorted_token_state_idx = {}   # (sorted_words, STATE) -> [(eid, ename, CITY)]
        self._collapsed_state_idx = {}      # (no_spaces_name, STATE) -> [(eid, ename, CITY)]
        self._stemmed_state_idx = {}        # (stemmed_name, STATE) -> [(eid, ename, CITY)]
        self._phonetic_state_idx = {}       # (metaphone_codes, STATE) -> [(eid, ename, CITY, nagg)]
        self._agg_sorted_by_state = {}      # STATE -> sorted [(nagg, eid, ename, CITY)]

        # In-memory trigram index (replaces RapidFuzz + pg_trgm)
        self._trigram_by_state = {}         # STATE -> {trigram -> set(eid)}
        self._trigram_names = {}            # eid -> (ename, nagg, STATE, CITY)

    def _load_min_name_similarity(self) -> float:
        """Load min Splink name similarity threshold from env with safe bounds."""
        raw = os.getenv("MATCH_MIN_NAME_SIM")
        if not raw:
            return self.DEFAULT_MIN_NAME_SIM
        try:
            val = float(raw)
        except ValueError:
            return self.DEFAULT_MIN_NAME_SIM
        if val < 0.0 or val > 1.0:
            return self.DEFAULT_MIN_NAME_SIM
        return val

    def _build_indexes(self):
        """Load F7 employers + crosswalk into in-memory lookup dicts."""
        if self._indexes_loaded:
            return

        print("  Building in-memory indexes...")

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, name_standard, name_aggressive,
                       UPPER(COALESCE(state, '')), UPPER(COALESCE(city, '')),
                       LEFT(COALESCE(zip, ''), 5)
                FROM f7_employers_deduped
                WHERE name_standard IS NOT NULL
            """)
            rows = cur.fetchall()

        collisions_ns = 0
        collisions_as = 0

        for eid, ename, nstd, nagg, st, ct, zp in rows:
            # name_standard + state -> list of candidates
            key_ns = (nstd, st)
            if key_ns not in self._name_state_idx:
                self._name_state_idx[key_ns] = []
            else:
                collisions_ns += 1
            self._name_state_idx[key_ns].append((eid, ename, ct))

            # name_standard + city + state -> list of candidates
            if ct:
                key_ncs = (nstd, ct, st)
                if key_ncs not in self._name_city_state_idx:
                    self._name_city_state_idx[key_ncs] = []
                self._name_city_state_idx[key_ncs].append((eid, ename))

            # name_standard + zip + state -> list of candidates
            if zp and len(zp) >= 5:
                key_nzs = (nstd, zp, st)
                if key_nzs not in self._name_zip_state_idx:
                    self._name_zip_state_idx[key_nzs] = []
                self._name_zip_state_idx[key_nzs].append((eid, ename, ct))

            # name_aggressive + state -> list of candidates
            if nagg:
                key_as = (nagg, st)
                if key_as not in self._agg_state_idx:
                    self._agg_state_idx[key_as] = []
                else:
                    collisions_as += 1
                self._agg_state_idx[key_as].append((eid, ename, ct))

            # --- New v5 indexes (built from same row data) ---
            if nagg and st:
                # Sorted token index (word reorder)
                sorted_tokens = " ".join(sorted(nagg.split()))
                self._sorted_token_state_idx.setdefault(
                    (sorted_tokens, st), []
                ).append((eid, ename, ct))

                # Collapsed spacing index (remove spaces/hyphens)
                import re as _re
                collapsed = _re.sub(r"[\s\-]", "", nagg)
                self._collapsed_state_idx.setdefault(
                    (collapsed, st), []
                ).append((eid, ename, ct))

                # Stemmed name index
                stemmed = _stem_name(nagg)
                self._stemmed_state_idx.setdefault(
                    (stemmed, st), []
                ).append((eid, ename, ct))

                # Phonetic index
                pk = _phonetic_key(nagg)
                if pk:
                    self._phonetic_state_idx.setdefault(
                        (pk, st), []
                    ).append((eid, ename, ct, nagg))

                # Truncation helper: sorted list per state for bisect
                self._agg_sorted_by_state.setdefault(st, []).append(
                    (nagg, eid, ename, ct)
                )

                # In-memory trigram inverted index (per state)
                if len(nagg) >= 3:
                    if st not in self._trigram_by_state:
                        self._trigram_by_state[st] = {}
                    state_tg = self._trigram_by_state[st]
                    for tg in _char_trigrams(nagg):
                        if tg not in state_tg:
                            state_tg[tg] = set()
                        state_tg[tg].add(eid)
                    self._trigram_names[eid] = (ename, nagg, st, ct)

        # Sort truncation lists for bisect lookups
        for st in self._agg_sorted_by_state:
            self._agg_sorted_by_state[st].sort()

        print(f"    name+state keys:      {len(self._name_state_idx):,} ({collisions_ns:,} collision adds)")
        print(f"    name+city+state keys:  {len(self._name_city_state_idx):,}")
        print(f"    name+zip+state keys:   {len(self._name_zip_state_idx):,}")
        print(f"    aggressive+state keys: {len(self._agg_state_idx):,} ({collisions_as:,} collision adds)")
        print(f"    sorted_token keys:     {len(self._sorted_token_state_idx):,}")
        print(f"    collapsed keys:        {len(self._collapsed_state_idx):,}")
        print(f"    stemmed keys:          {len(self._stemmed_state_idx):,}")
        print(f"    phonetic keys:         {len(self._phonetic_state_idx):,}")
        print(f"    trigram employers:     {len(self._trigram_names):,}")

        # Load EIN index from crosswalk (EIN is usually unique per employer)
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT ein, f7_employer_id
                FROM corporate_identifier_crosswalk
                WHERE ein IS NOT NULL AND f7_employer_id IS NOT NULL
            """)
            for ein, fid in cur.fetchall():
                if ein not in self._ein_idx:
                    self._ein_idx[ein] = fid

        print(f"    EIN keys:              {len(self._ein_idx):,}")
        self._indexes_loaded = True

    def match_batch(self, records: List[Dict]) -> List[Dict]:
        """
        Match a batch of source records against F7 employers.

        Each record must have: id, name, state, city, zip, naics, ein, address
        Returns list of match dicts with source_id, target_id, method, score, etc.
        """
        self._build_indexes()

        results = []
        unmatched = []
        self.stats["total"] += len(records)

        # Pass 1: In-memory best-match matching (tiers 1-4)
        for i, rec in enumerate(records):
            result = self._match_best(rec)
            if result:
                results.append(result)
                self._record_match(result)
            else:
                unmatched.append(rec)

            if (i + 1) % 50000 == 0:
                print(f"    Exact pass: {i+1:,}/{len(records):,} "
                      f"-- {len(results):,} matched so far")

        print(f"  Exact matching: {len(results):,}/{len(records):,} "
              f"({len(results)/max(len(records),1)*100:.1f}%)")
        if self.stats["collisions_resolved"] or self.stats["collisions_ambiguous"]:
            print(f"  Collisions: {self.stats['collisions_resolved']:,} resolved by city, "
                  f"{self.stats['collisions_ambiguous']:,} ambiguous")
        print(f"  Remaining for fuzzy: {len(unmatched):,}")

        # Pass 2: Batched fuzzy matching (tier 5)
        if unmatched and not self.skip_fuzzy:
            fuzzy_results = self._fuzzy_batch(unmatched)
            for result in fuzzy_results:
                results.append(result)
                self._record_match(result)
            print(f"  Fuzzy matching: {len(fuzzy_results):,} additional matches")

        # Flush remaining log buffer
        if not self.dry_run:
            self._flush_log()

        return results

    def _match_best(self, rec: Dict) -> Optional[Dict]:
        """
        Evaluate ALL tiers and return the best (most specific) match.

        Tier priority: EIN(100) > name+city+state(90) > name+zip+state(85) > name+state(80) > aggressive+state(60)
        Within a tier, city disambiguation resolves multi-candidate collisions.
        """
        source_id = str(rec["id"])
        name = rec.get("name") or ""
        state = (rec.get("state") or "").upper().strip()
        city = (rec.get("city") or "").upper().strip()
        ein = (rec.get("ein") or "").strip()

        name_std = normalize_name_standard(name)
        name_agg = normalize_name_aggressive(name)
        zip5 = (rec.get("zip") or "").strip()[:5]

        best = None  # (tier_rank, result_dict)

        # Tier 1: EIN exact match (specificity 100)
        if ein and len(ein) >= 8:
            fid = self._ein_idx.get(ein)
            if fid:
                result = self._make_result(
                    source_id, fid, "EIN_EXACT", "deterministic", "HIGH", 1.0,
                    {"ein": ein, "source_name": name}
                )
                best = (TIER_RANK["EIN_EXACT"], result)

        # Tier 2: name_standard + city + state (specificity 90)
        if name_std and city and state and (best is None or best[0] < TIER_RANK["NAME_CITY_STATE_EXACT"]):
            candidates = self._name_city_state_idx.get((name_std, city, state))
            if candidates:
                if len(candidates) == 1:
                    eid, ename = candidates[0]
                    result = self._make_result(
                        source_id, eid, "NAME_CITY_STATE_EXACT", "deterministic", "HIGH", 0.95,
                        {"source_name": name, "target_name": ename, "city": city, "state": state}
                    )
                    new_rank = TIER_RANK["NAME_CITY_STATE_EXACT"]
                    if best is None or new_rank > best[0]:
                        best = (new_rank, result)
                else:
                    # Multiple candidates with same name+city+state — use
                    # disambiguation (Splink or flag ambiguous) instead of
                    # silently picking the first one.
                    cands_3 = [(c[0], c[1], city) for c in candidates]
                    resolved = self._disambiguate(cands_3, city, source_id, name, state,
                                                   "NAME_CITY_STATE_EXACT", 0.95,
                                                   source_rec=rec)
                    if resolved:
                        new_rank = TIER_RANK["NAME_CITY_STATE_EXACT"]
                        if best is None or new_rank > best[0]:
                            best = (new_rank, resolved)

        # Tier 2.5: name_standard + zip + state (specificity 85)
        if name_std and zip5 and len(zip5) >= 5 and state and (best is None or best[0] < TIER_RANK["NAME_ZIP_STATE"]):
            candidates = self._name_zip_state_idx.get((name_std, zip5, state))
            if candidates:
                resolved = self._disambiguate(candidates, city, source_id, name, state,
                                               "NAME_ZIP_STATE", 0.93,
                                               source_rec=rec)
                if resolved:
                    new_rank = TIER_RANK["NAME_ZIP_STATE"]
                    if best is None or new_rank > best[0]:
                        best = (new_rank, resolved)

        # Tier 3: name_standard + state with city disambiguation (specificity 80)
        if name_std and state and (best is None or best[0] < TIER_RANK["NAME_STATE_EXACT"]):
            candidates = self._name_state_idx.get((name_std, state))
            if candidates:
                resolved = self._disambiguate(candidates, city, source_id, name, state,
                                               "NAME_STATE_EXACT", 0.90,
                                               source_rec=rec)
                if resolved:
                    new_rank = TIER_RANK["NAME_STATE_EXACT"]
                    if best is None or new_rank > best[0]:
                        best = (new_rank, resolved)

        # Tier 4: name_aggressive + state with city disambiguation (specificity 60)
        if name_agg and len(name_agg) >= 6 and state and (best is None or best[0] < TIER_RANK["NAME_AGGRESSIVE_STATE"]):
            candidates = self._agg_state_idx.get((name_agg, state))
            if candidates:
                resolved = self._disambiguate(candidates, city, source_id, name, state,
                                               "NAME_AGGRESSIVE_STATE", 0.75,
                                               source_rec=rec)
                if resolved:
                    new_rank = TIER_RANK["NAME_AGGRESSIVE_STATE"]
                    if best is None or new_rank > best[0]:
                        best = (new_rank, resolved)

        # --- New v5 deterministic tiers (ranks 50-57) ---

        # Tier 4.1: SORTED_TOKEN_STATE (rank 57) — word reorder
        if name_agg and len(name_agg) >= 6 and state and (best is None or best[0] < TIER_RANK["SORTED_TOKEN_STATE"]):
            sorted_tokens = " ".join(sorted(name_agg.split()))
            if sorted_tokens != name_agg:  # only if sorting changed something
                candidates = self._sorted_token_state_idx.get((sorted_tokens, state))
                if candidates:
                    resolved = self._disambiguate(candidates, city, source_id, name, state,
                                                   "SORTED_TOKEN_STATE", 0.85,
                                                   source_rec=rec)
                    if resolved:
                        new_rank = TIER_RANK["SORTED_TOKEN_STATE"]
                        if best is None or new_rank > best[0]:
                            best = (new_rank, resolved)

        # Tier 4.2: COLLAPSED_SPACING_STATE (rank 55) — spacing/hyphen
        if name_agg and len(name_agg) >= 6 and state and (best is None or best[0] < TIER_RANK["COLLAPSED_SPACING_STATE"]):
            import re as _re
            collapsed = _re.sub(r"[\s\-]", "", name_agg)
            if collapsed != name_agg.replace(" ", "").replace("-", "") or len(name_agg.split()) > 1:
                candidates = self._collapsed_state_idx.get((collapsed, state))
                if candidates:
                    resolved = self._disambiguate(candidates, city, source_id, name, state,
                                                   "COLLAPSED_SPACING_STATE", 0.82,
                                                   source_rec=rec)
                    if resolved:
                        new_rank = TIER_RANK["COLLAPSED_SPACING_STATE"]
                        if best is None or new_rank > best[0]:
                            best = (new_rank, resolved)

        # Tier 4.3: TRUNCATED_NAME_STATE (rank 54) — prefix matching
        if name_agg and state and len(name_agg) >= 10 and (best is None or best[0] < TIER_RANK["TRUNCATED_NAME_STATE"]):
            trunc_match = self._try_truncation_match(name_agg, state, city, source_id, name, rec)
            if trunc_match:
                new_rank = TIER_RANK["TRUNCATED_NAME_STATE"]
                if best is None or new_rank > best[0]:
                    best = (new_rank, trunc_match)

        # Tier 4.4: STRIPPED_LEADING_NUMS_STATE (rank 53) — OSHA activity IDs
        if name and state and (best is None or best[0] < TIER_RANK["STRIPPED_LEADING_NUMS_STATE"]):
            import re as _re
            stripped_name = _re.sub(r"^\d+\s+", "", name.strip())
            if stripped_name != name.strip() and len(stripped_name) >= 3:
                stripped_agg = normalize_name_aggressive(stripped_name)
                if stripped_agg:
                    candidates = self._agg_state_idx.get((stripped_agg, state))
                    if candidates:
                        resolved = self._disambiguate(candidates, city, source_id, name, state,
                                                       "STRIPPED_LEADING_NUMS_STATE", 0.80,
                                                       source_rec=rec)
                        if resolved:
                            new_rank = TIER_RANK["STRIPPED_LEADING_NUMS_STATE"]
                            if best is None or new_rank > best[0]:
                                best = (new_rank, resolved)

        # Tier 4.5: STEMMED_NAME_STATE (rank 52) — plural/suffix morphology
        if name_agg and len(name_agg) >= 6 and state and (best is None or best[0] < TIER_RANK["STEMMED_NAME_STATE"]):
            stemmed = _stem_name(name_agg)
            if stemmed != name_agg:  # only if stemming changed something
                candidates = self._stemmed_state_idx.get((stemmed, state))
                if candidates:
                    resolved = self._disambiguate(candidates, city, source_id, name, state,
                                                   "STEMMED_NAME_STATE", 0.78,
                                                   source_rec=rec)
                    if resolved:
                        new_rank = TIER_RANK["STEMMED_NAME_STATE"]
                        if best is None or new_rank > best[0]:
                            best = (new_rank, resolved)

        # Tier 4.6: PHONETIC_STATE (rank 50) — typo catching via phonetic encoding
        if name_agg and len(name_agg) >= 6 and state and HAS_JELLYFISH and (best is None or best[0] < TIER_RANK["PHONETIC_STATE"]):
            phon_match = self._try_phonetic_match(name_agg, state, city, source_id, name, rec)
            if phon_match:
                new_rank = TIER_RANK["PHONETIC_STATE"]
                if best is None or new_rank > best[0]:
                    best = (new_rank, phon_match)

        return best[1] if best else None

    def _try_truncation_match(self, name_agg, state, city, source_id, name, rec):
        """Truncation tier: match if shorter name is prefix of longer (min 10 chars)."""
        import bisect as _bisect
        candidates = []

        # Direction 1: source is prefix of some target (source truncated)
        state_list = self._agg_sorted_by_state.get(state, [])
        if state_list:
            pos = _bisect.bisect_left(state_list, (name_agg,))
            while pos < len(state_list) and state_list[pos][0].startswith(name_agg):
                t_nagg, t_eid, t_ename, t_ct = state_list[pos]
                if t_nagg != name_agg:  # skip exact (handled by earlier tiers)
                    candidates.append((t_eid, t_ename, t_ct))
                pos += 1

        # Direction 2: some target is prefix of source (target truncated)
        for plen in range(10, len(name_agg)):
            prefix = name_agg[:plen]
            hits = self._agg_state_idx.get((prefix, state))
            if hits:
                for h in hits:
                    candidates.append(h)

        if not candidates:
            return None

        # Deduplicate by employer_id
        seen = set()
        deduped = []
        for c in candidates:
            if c[0] not in seen:
                seen.add(c[0])
                deduped.append(c)

        return self._disambiguate(deduped, city, source_id, name, state,
                                   "TRUNCATED_NAME_STATE", 0.80, source_rec=rec)

    def _try_phonetic_match(self, name_agg, state, city, source_id, name, rec):
        """Phonetic tier: match via Metaphone encoding with secondary validation."""
        pk = _phonetic_key(name_agg)
        if not pk:
            return None

        candidates = self._phonetic_state_idx.get((pk, state))
        if not candidates:
            return None

        # Secondary validation: word count within +/-1 AND bigram Jaccard > 0.5
        source_wc = len(name_agg.split())
        validated = []
        for eid, ename, ct, target_nagg in candidates:
            # Skip if this is an exact aggressive match (handled by tier 4)
            if target_nagg == name_agg:
                continue
            target_wc = len(target_nagg.split())
            if abs(source_wc - target_wc) > 1:
                continue
            jac = _jaccard_bigrams(name_agg, target_nagg)
            if jac < 0.5:
                continue
            validated.append((eid, ename, ct))

        if not validated:
            return None

        return self._disambiguate(validated, city, source_id, name, state,
                                   "PHONETIC_STATE", 0.75, source_rec=rec)

    def _disambiguate(self, candidates: List[Tuple], source_city: str,
                      source_id: str, source_name: str, state: str,
                      method: str, base_score: float,
                      source_rec: Optional[Dict] = None) -> Optional[Dict]:
        """
        Resolve multi-candidate collisions: city -> Splink -> ambiguous.

        Resolution order:
        1. Single candidate: accept directly.
        2. City narrows to 1: accept with CITY_RESOLVED suffix.
        3. Splink disambiguation: compare source against remaining candidates.
        4. Still ambiguous: flag as AMBIGUOUS with LOW confidence.
        """
        if len(candidates) == 1:
            eid, ename = candidates[0][0], candidates[0][1]
            return self._make_result(
                source_id, eid, method, "deterministic",
                self._band_for_score(base_score), base_score,
                {"source_name": source_name, "target_name": ename, "state": state}
            )

        # Step 1: Try city disambiguation
        remaining = candidates
        if source_city:
            city_matches = [c for c in candidates if c[2] == source_city]
            if len(city_matches) == 1:
                eid, ename = city_matches[0][0], city_matches[0][1]
                self.stats["collisions_resolved"] += 1
                return self._make_result(
                    source_id, eid, method + "_CITY_RESOLVED", "deterministic",
                    self._band_for_score(base_score), base_score,
                    {
                        "source_name": source_name,
                        "target_name": ename,
                        "state": state,
                        "city": source_city,
                        "candidates": len(candidates),
                        "resolved_by": "city",
                    }
                )
            if len(city_matches) > 1:
                remaining = city_matches

        # Step 2: Try Splink disambiguation (small candidate set)
        if source_rec and len(remaining) <= 10:
            splink_result = self._splink_disambiguate(
                source_rec, remaining, source_id, source_name, state, method
            )
            if splink_result:
                return splink_result

        # Step 3: Give up -- flag as ambiguous
        self.stats["collisions_ambiguous"] += 1
        return self._make_result(
            source_id, "AMBIGUOUS", f"AMBIGUOUS_{method}", "deterministic", "LOW", 0.0,
            {
                "source_name": source_name,
                "state": state,
                "candidate_count": len(remaining),
                "candidate_ids": sorted(str(c[0]) for c in remaining),
                "ambiguous": True,
            }
        )

    def _splink_disambiguate(self, source_rec: Dict, candidates: List[Tuple],
                             source_id: str, source_name: str, state: str,
                             method: str) -> Optional[Dict]:
        """
        Use Splink multi-field comparison to pick the best candidate from a
        small collision set (2-10 candidates).

        Returns a match result if Splink finds a clear winner (top probability
        significantly above second-best). Returns None if Splink is unavailable
        or candidates remain tied.
        """
        if not self._splink_available():
            return None

        import pandas as pd
        from splink import DuckDBAPI, Linker

        model_file = self._get_splink_model_path()
        if not model_file:
            return None

        name_std = normalize_name_standard(source_rec.get("name") or "")
        source_city = (source_rec.get("city") or "").upper().strip()
        zip_code = (source_rec.get("zip") or "").strip()
        naics = (source_rec.get("naics") or "").strip()
        address = (source_rec.get("address") or "").strip()

        df_source = pd.DataFrame([{
            "id": str(source_id),
            "name_normalized": name_std,
            "state": state,
            "city": source_city,
            "zip": zip_code,
            "naics": naics,
            "street_address": address,
        }])

        # Build target DataFrame from candidate tuples: (eid, ename, city)
        # Also build a lookup for candidate names by ID
        cand_names = {}
        target_rows = []
        for cand in candidates:
            eid, ename = str(cand[0]), str(cand[1])
            cand_city = str(cand[2]) if len(cand) > 2 else ""
            cand_names[eid] = ename
            target_rows.append({
                "id": eid,
                "name_normalized": normalize_name_standard(ename),
                "state": state,
                "city": cand_city,
                "zip": "",
                "naics": "",
                "street_address": "",
            })
        df_target = pd.DataFrame(target_rows)

        try:
            linker = Linker(
                [df_source, df_target],
                settings=str(model_file),
                db_api=DuckDBAPI(),
                set_up_basic_logging=False,
            )
            df_matches = linker.inference.predict(
                threshold_match_probability=0.01  # low threshold -- we want to rank all candidates
            ).as_pandas_dataframe()
        except Exception:
            return None

        if df_matches.empty:
            return None

        df_matches = df_matches.sort_values("match_probability", ascending=False)
        top = df_matches.iloc[0]
        top_prob = float(top["match_probability"])

        # Require clear winner: top must beat second by >= 0.10
        if len(df_matches) > 1:
            second_prob = float(df_matches.iloc[1]["match_probability"])
            if top_prob - second_prob < 0.10:
                return None  # too close -- let caller flag as ambiguous

        target_id = str(top.get("id_r", ""))
        target_name = cand_names.get(target_id, "")

        # Guard against geography-dominated false positives: require minimum
        # name similarity even in collision disambiguation mode.
        # Mirror fuzzy-batch floor behavior by using Splink-normalized names
        # when present in output, with standard-normalized fallback.
        from rapidfuzz import fuzz as _rf_fuzz
        source_name_norm = str(top.get("name_normalized_l") or name_std)
        target_name_norm = str(top.get("name_normalized_r") or normalize_name_standard(target_name))
        name_similarity = _rf_fuzz.token_sort_ratio(source_name_norm, target_name_norm) / 100.0
        if name_similarity < self.min_name_similarity:
            return None

        self.stats["collisions_resolved"] += 1
        return self._make_result(
            source_id, target_id, method + "_SPLINK_RESOLVED", "deterministic",
            self._band_for_score(top_prob), top_prob,
            {
                "source_name": source_name,
                "target_name": target_name,
                "state": state,
                "candidates": len(candidates),
                "match_probability": round(top_prob, 4),
                "name_similarity": round(name_similarity, 3),
                "resolved_by": "splink",
            }
        )

    def _splink_available(self) -> bool:
        """Check if Splink + model are available (cached after first check)."""
        if hasattr(self, "_splink_ok"):
            return self._splink_ok
        try:
            import splink  # noqa: F401
            self._splink_ok = self._get_splink_model_path() is not None
        except ImportError:
            self._splink_ok = False
        return self._splink_ok

    def _get_splink_model_path(self) -> Optional[Path]:
        """Resolve path to pre-trained Splink model JSON."""
        if hasattr(self, "_splink_model_path"):
            return self._splink_model_path
        try:
            from scripts.matching.splink_config import SCENARIOS
            cfg = SCENARIOS.get("adaptive_fuzzy", {})
            mp = cfg.get("model_path")
            if not mp:
                self._splink_model_path = None
                return None
            model_file = Path(mp)
            if not model_file.is_absolute():
                model_file = Path(__file__).resolve().parent.parent.parent / model_file
            self._splink_model_path = model_file if model_file.exists() else None
        except Exception:
            self._splink_model_path = None
        return self._splink_model_path

    def _load_f7_target_df(self):
        """Load F7 employers into a DataFrame for Splink matching (cached)."""
        if hasattr(self, "_f7_target_df"):
            return self._f7_target_df

        import pandas as pd

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id AS id,
                       COALESCE(name_aggressive, name_standard) AS name_normalized,
                       UPPER(COALESCE(state, '')) AS state,
                       UPPER(COALESCE(city, '')) AS city,
                       COALESCE(zip, '') AS zip,
                       COALESCE(naics, '') AS naics,
                       COALESCE(street, '') AS street_address
                FROM f7_employers_deduped
                WHERE name_standard IS NOT NULL
            """)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

        df = pd.DataFrame(rows, columns=cols)
        df = df.fillna("")
        # Ensure id is string (f7_employer_id is TEXT)
        df["id"] = df["id"].astype(str)

        self._f7_target_df = df
        print(f"  Splink: loaded {len(df):,} F7 target records")
        return df

    def _fuzzy_batch_splink(self, records: List[Dict],
                            batch_size: int = 10000) -> Tuple[List[Dict], List[Dict]]:
        """
        Tier 5a: Batched fuzzy matching using Splink probabilistic model.

        Uses the pre-trained adaptive_fuzzy model for multi-field comparison
        (name + state + city + zip + naics + address).

        Returns (matched_results, still_unmatched_records) so that trigram
        can be tried on the leftovers.
        """
        import pandas as pd
        from splink import DuckDBAPI, Linker

        model_file = self._get_splink_model_path()
        if not model_file:
            return [], records

        df_target = self._load_f7_target_df()

        # Build source DataFrame
        source_rows = []
        for rec in records:
            name = rec.get("name") or ""
            state = (rec.get("state") or "").upper().strip()
            name_std = normalize_name_standard(name)
            if not name_std or not state or len(name_std) < 3:
                continue
            source_rows.append({
                "id": str(rec["id"]),
                "name_normalized": name_std,
                "state": state,
                "city": (rec.get("city") or "").upper().strip(),
                "zip": (rec.get("zip") or "").strip(),
                "naics": (rec.get("naics") or "").strip(),
                "street_address": (rec.get("address") or "").strip(),
            })

        if not source_rows:
            return [], records

        print(f"  Splink fuzzy: processing {len(source_rows):,} candidates"
              f" in batches of {batch_size}")

        results = []
        matched_source_ids = set()

        for batch_start in range(0, len(source_rows), batch_size):
            batch = source_rows[batch_start:batch_start + batch_size]
            df_source = pd.DataFrame(batch)

            try:
                linker = Linker(
                    [df_source, df_target],
                    settings=str(model_file),
                    db_api=DuckDBAPI(),
                    set_up_basic_logging=False,
                )
                df_matches = linker.inference.predict(
                    threshold_match_probability=0.60
                ).as_pandas_dataframe()
            except Exception as e:
                print(f"    Splink batch error: {e}")
                continue

            if df_matches.empty:
                done = min(batch_start + batch_size, len(source_rows))
                print(f"    Splink: {done:,}/{len(source_rows):,} -- "
                      f"{len(results):,} matches")
                continue

            # Filter: require minimum name similarity to prevent
            # geography-only matches (the model overweights city/zip).
            from rapidfuzz import fuzz as _rf_fuzz
            if "name_normalized_l" in df_matches.columns and "name_normalized_r" in df_matches.columns:
                df_matches = df_matches[
                    df_matches.apply(
                        lambda r: _rf_fuzz.token_sort_ratio(
                            str(r.get("name_normalized_l", "")),
                            str(r.get("name_normalized_r", "")),
                        ) / 100.0 >= self.min_name_similarity,
                        axis=1,
                    )
                ]

            # Keep best match per source_id (highest probability)
            df_matches = df_matches.sort_values(
                "match_probability", ascending=False
            )
            df_matches = df_matches.drop_duplicates(
                subset=["id_l"], keep="first"
            )

            for _, row in df_matches.iterrows():
                source_id = str(row["id_l"])
                target_id = str(row["id_r"])
                prob = float(row["match_probability"])
                src_name = str(row.get("name_normalized_l", ""))
                tgt_name = str(row.get("name_normalized_r", ""))
                name_sim = _rf_fuzz.token_sort_ratio(src_name, tgt_name) / 100.0
                band = self._band_for_score(prob)

                evidence = {
                    "source_name": src_name,
                    "target_name": tgt_name,
                    "state": row.get("state_l", ""),
                    "match_probability": round(prob, 4),
                    "name_similarity": round(name_sim, 3),
                }

                results.append(self._make_result(
                    source_id, target_id,
                    "FUZZY_SPLINK_ADAPTIVE", "probabilistic", band, prob,
                    evidence
                ))
                matched_source_ids.add(source_id)

            done = min(batch_start + batch_size, len(source_rows))
            print(f"    Splink: {done:,}/{len(source_rows):,} -- "
                  f"{len(results):,} matches")

        # Records Splink didn't match fall through to trigram
        still_unmatched = [
            r for r in records if str(r["id"]) not in matched_source_ids
        ]

        return results, still_unmatched

    def _fuzzy_batch_rapidfuzz(self, records: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """
        Tier 5a: Batched fuzzy matching using RapidFuzz with SQL-style blocking.

        Replaces Splink probabilistic matching with direct name similarity scoring.
        Uses the same 3 blocking rules to generate candidate pairs, then scores
        with rapidfuzz.fuzz.token_sort_ratio and applies the 0.80 floor.

        Tie-breaking for equal name similarity: city match > zip match > NAICS match.

        Returns (matched_results, still_unmatched_records) so that trigram
        can be tried on the leftovers.
        """
        from rapidfuzz import fuzz as _rf_fuzz
        try:
            from tqdm import tqdm
        except ImportError:
            tqdm = None

        # Load F7 targets (reuses cached DataFrame loader, convert to dicts)
        f7_targets = self._load_f7_targets_for_rapidfuzz()

        # Build source records
        source_rows = []
        source_lookup = {}  # id -> source row for tie-breaking fields
        for rec in records:
            name = rec.get("name") or ""
            state = (rec.get("state") or "").upper().strip()
            name_std = normalize_name_standard(name)
            if not name_std or not state or len(name_std) < 3:
                continue
            sid = str(rec["id"])
            city = (rec.get("city") or "").upper().strip()
            zipcode = (rec.get("zip") or "").strip()[:5]
            naics = (rec.get("naics") or "").strip()
            source_rows.append({
                "id": sid,
                "name_normalized": name_std,
                "state": state,
                "city": city,
                "zip": zipcode,
                "naics": naics,
            })
            source_lookup[sid] = {
                "name": name_std, "state": state, "city": city,
                "zip": zipcode, "naics": naics,
            }

        if not source_rows:
            return [], records

        print(f"  RapidFuzz: processing {len(source_rows):,} candidates "
              f"against {len(f7_targets):,} targets")

        # Build blocking indexes over F7 targets
        idx_state_name3 = defaultdict(list)
        idx_state_city = defaultdict(list)
        idx_zip3_name2 = defaultdict(list)

        for t in f7_targets:
            tid = t["id"]
            tname = t["name_normalized"]
            tstate = t["state"]
            tcity = t["city"]
            tzip = t["zip"]
            tnaics = t["naics"]
            entry = (tid, tname, tcity, tzip, tnaics)

            tname_upper = tname.upper()
            if tstate and tname and len(tname) >= 3:
                idx_state_name3[(tstate, tname_upper[:3])].append(entry)
            if tstate and tcity:
                idx_state_city[(tstate, tcity)].append(entry)
            if tzip and len(tzip) >= 3 and tname and len(tname) >= 2:
                idx_zip3_name2[(tzip[:3], tname_upper[:2])].append(entry)

        # Score candidates
        results = []
        matched_source_ids = set()

        iterator = source_rows
        if tqdm is not None:
            iterator = tqdm(source_rows, desc="  RapidFuzz scoring",
                            unit="rec", smoothing=0.1)

        for src in iterator:
            sid = src["id"]
            sname = src["name_normalized"]
            sstate = src["state"]
            scity = src["city"]
            szip = src["zip"]
            snaics = src["naics"]
            sname_upper = sname.upper()

            # Collect candidates from all blocking rules (deduplicated by target id)
            seen_tids = set()
            candidates = []

            # Block 1: state + name[:3]
            for entry in idx_state_name3.get((sstate, sname_upper[:3]), []):
                if entry[0] not in seen_tids:
                    seen_tids.add(entry[0])
                    candidates.append(entry)

            # Block 2: state + city
            if scity:
                for entry in idx_state_city.get((sstate, scity), []):
                    if entry[0] not in seen_tids:
                        seen_tids.add(entry[0])
                        candidates.append(entry)

            # Block 3: zip[:3] + name[:2]
            if szip and len(szip) >= 3:
                for entry in idx_zip3_name2.get((szip[:3], sname_upper[:2]), []):
                    if entry[0] not in seen_tids:
                        seen_tids.add(entry[0])
                        candidates.append(entry)

            if not candidates:
                continue

            # Score all candidates and find best match with tie-breaking
            best_sim = 0.0
            best_tiebreak = (-1, -1, -1)  # (city_match, zip_match, naics_match)
            best_match = None

            for tid, tname, tcity, tzip, tnaics in candidates:
                sim = _rf_fuzz.token_sort_ratio(sname, tname) / 100.0
                if sim < self.min_name_similarity:
                    continue

                # Tie-breaking: city > zip > naics (1 if match, 0 if not)
                tb = (
                    1 if (scity and tcity and scity == tcity) else 0,
                    1 if (szip and tzip and szip == tzip) else 0,
                    1 if (snaics and tnaics and snaics == tnaics) else 0,
                )

                if sim > best_sim or (sim == best_sim and tb > best_tiebreak):
                    best_sim = sim
                    best_tiebreak = tb
                    best_match = (tid, tname, sim)

            if best_match:
                tid, tname, sim = best_match
                band = self._band_for_score(sim)
                evidence = {
                    "source_name": sname,
                    "target_name": tname,
                    "state": sstate,
                    "name_similarity": round(sim, 3),
                    "match_method_detail": "rapidfuzz_token_sort_ratio",
                }
                results.append(self._make_result(
                    sid, tid,
                    "FUZZY_SPLINK_ADAPTIVE", "probabilistic", band, sim,
                    evidence
                ))
                matched_source_ids.add(sid)

        print(f"  RapidFuzz: {len(results):,} matches from "
              f"{len(source_rows):,} candidates")

        # Records not matched fall through to trigram
        still_unmatched = [
            r for r in records if str(r["id"]) not in matched_source_ids
        ]

        return results, still_unmatched

    def _load_f7_targets_for_rapidfuzz(self):
        """Load F7 employer targets as list of dicts for RapidFuzz blocking."""
        if hasattr(self, "_f7_targets_rf"):
            return self._f7_targets_rf

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id AS id,
                       COALESCE(name_aggressive, name_standard) AS name_normalized,
                       UPPER(COALESCE(state, '')) AS state,
                       UPPER(COALESCE(city, '')) AS city,
                       COALESCE(zip, '') AS zip,
                       COALESCE(naics, '') AS naics
                FROM f7_employers_deduped
                WHERE name_standard IS NOT NULL
            """)
            cols = [d[0] for d in cur.description]
            rows = cur.fetchall()

        targets = [dict(zip(cols, row)) for row in rows]
        for t in targets:
            t["id"] = str(t["id"])
        self._f7_targets_rf = targets
        print(f"  RapidFuzz: loaded {len(targets):,} F7 target records")
        return targets

    def _fuzzy_batch_inmemory_trigram(self, records: List[Dict],
                                      top_k: int = 20,
                                      min_score: float = 0.90) -> List[Dict]:
        """
        Tier 5: In-memory trigram fuzzy matching.

        Replaces RapidFuzz blocked matching + pg_trgm SQL with a single
        in-memory approach using an inverted character trigram index.

        For each record:
        1. Compute trigrams of aggressive-normalized name
        2. Find candidates via inverted index (state-partitioned)
        3. Take top-K by trigram overlap count
        4. Score with composite (JaroWinkler + token_set + ratio)
        5. Accept best above threshold
        """
        try:
            from rapidfuzz import fuzz as _rf_fuzz
            from rapidfuzz.distance import JaroWinkler as _JW
            has_rf = True
        except ImportError:
            has_rf = False

        from collections import Counter as _Counter

        results = []
        total = len(records)

        for i, rec in enumerate(records):
            rec_name = rec.get("name") or ""
            state = (rec.get("state") or "").upper().strip()
            city = (rec.get("city") or "").upper().strip()
            source_id = str(rec["id"])

            name_agg = normalize_name_aggressive(rec_name)
            if not name_agg or not state or len(name_agg) < 3:
                continue

            # Step 1: compute source trigrams
            source_tgs = _char_trigrams(name_agg)
            if not source_tgs:
                continue

            # Step 2: count shared trigrams per candidate (state-filtered)
            state_tg_idx = self._trigram_by_state.get(state)
            if not state_tg_idx:
                continue

            candidate_overlap = _Counter()
            for tg in source_tgs:
                eid_set = state_tg_idx.get(tg)
                if eid_set:
                    for eid in eid_set:
                        candidate_overlap[eid] += 1

            if not candidate_overlap:
                continue

            # Step 3: take top-K by overlap, pre-filter on minimum overlap
            min_overlap = max(3, int(len(source_tgs) * 0.3))
            top_candidates = [
                (eid, cnt) for eid, cnt in candidate_overlap.most_common(top_k * 2)
                if cnt >= min_overlap
            ][:top_k]

            if not top_candidates:
                continue

            # Step 4: score each candidate
            best_score = 0.0
            best_match = None

            for eid, overlap_count in top_candidates:
                entry = self._trigram_names.get(eid)
                if not entry:
                    continue
                target_name, target_nagg, target_state, target_city = entry

                if has_rf:
                    jw = _JW.similarity(name_agg, target_nagg)
                    tsr = _rf_fuzz.token_set_ratio(name_agg, target_nagg) / 100.0
                    ratio = _rf_fuzz.ratio(name_agg, target_nagg) / 100.0
                    composite = 0.35 * jw + 0.35 * tsr + 0.30 * ratio
                else:
                    from difflib import SequenceMatcher
                    composite = SequenceMatcher(None, name_agg, target_nagg).ratio()

                if composite > best_score and composite >= min_score:
                    best_score = composite
                    best_match = (eid, target_name, composite, target_city)

            if best_match:
                eid, target_name, score, target_city = best_match
                band = self._band_for_score(score)
                results.append(self._make_result(
                    source_id, eid,
                    "FUZZY_INMEMORY_TRIGRAM", "probabilistic", band, score,
                    {
                        "source_name": rec_name,
                        "target_name": target_name,
                        "state": state,
                        "name_similarity": round(score, 3),
                        "match_method_detail": "inmemory_trigram_composite",
                    }
                ))

            if (i + 1) % 50000 == 0:
                print(f"    InMemTrigram: {i+1:,}/{total:,} -- "
                      f"{len(results):,} matched so far")

        return results

    def _fuzzy_batch(self, records: List[Dict], batch_size: int = 200) -> List[Dict]:
        """Tier 5 fuzzy matching: in-memory trigram (v5), with legacy fallback."""
        # Primary: in-memory trigram index (fast)
        try:
            results = self._fuzzy_batch_inmemory_trigram(records)
            if results:
                print(f"  InMemTrigram matched {len(results):,}")
            return results
        except Exception as e:
            print(f"  InMemTrigram error, falling back to legacy: {e}")

        # Legacy fallback: RapidFuzz + pg_trgm
        results = []
        remaining = records
        try:
            rf_results, remaining = self._fuzzy_batch_rapidfuzz(records)
            results.extend(rf_results)
            if rf_results:
                print(f"  RapidFuzz matched {len(rf_results):,}, "
                      f"{len(remaining):,} remaining for trigram")
        except Exception as e:
            print(f"  RapidFuzz error, falling back to trigram: {e}")
            remaining = records

        if remaining:
            trigram_results = self._fuzzy_batch_trigram(
                remaining, batch_size=batch_size
            )
            results.extend(trigram_results)

        return results

    def _fuzzy_batch_trigram(self, records: List[Dict], batch_size: int = 200) -> List[Dict]:
        """
        Tier 5: Batched fuzzy matching using pg_trgm.

        Creates a temp table of unmatched records, then JOINs against
        f7_employers_deduped using trigram similarity.
        """
        results = []

        # Prep: normalize all records
        prepped = []
        for rec in records:
            name_std = normalize_name_standard(rec.get("name") or "")
            state = (rec.get("state") or "").upper().strip()
            if name_std and state and len(name_std) >= 3:
                prepped.append((str(rec["id"]), name_std, state, rec.get("name") or ""))

        if not prepped:
            return results

        print(f"  Fuzzy: processing {len(prepped):,} candidates in batches of {batch_size}")

        with self.conn.cursor() as cur:
            # Check pg_trgm availability
            try:
                cur.execute("SELECT similarity('test', 'test')")
            except Exception:
                self.conn.rollback()
                print("  WARNING: pg_trgm not available, skipping fuzzy matching")
                return results

            # Process in batches via temp table
            for batch_start in range(0, len(prepped), batch_size):
                batch = prepped[batch_start:batch_start + batch_size]

                # Create temp table for this batch
                cur.execute("""
                    CREATE TEMP TABLE IF NOT EXISTS _fuzzy_batch (
                        source_id TEXT,
                        name_std TEXT,
                        state TEXT,
                        orig_name TEXT
                    ) ON COMMIT DELETE ROWS
                """)
                cur.execute("TRUNCATE _fuzzy_batch")

                from psycopg2.extras import execute_batch
                execute_batch(cur, """
                    INSERT INTO _fuzzy_batch (source_id, name_std, state, orig_name)
                    VALUES (%s, %s, %s, %s)
                """, batch, page_size=500)

                # Join using trigram similarity
                # Note: single % for pg_trgm operator (no params = no escaping)
                cur.execute(
                    "SELECT DISTINCT ON (b.source_id)"
                    "  b.source_id, b.orig_name,"
                    "  f.employer_id, f.employer_name,"
                    "  b.state,"
                    "  similarity(f.name_standard, b.name_std) as sim"
                    " FROM _fuzzy_batch b"
                    " JOIN f7_employers_deduped f"
                    "   ON UPPER(f.state) = b.state"
                    "   AND f.name_standard % b.name_std"
                    "   AND similarity(f.name_standard, b.name_std) >= 0.4"
                    " ORDER BY b.source_id, sim DESC"
                )
                rows = cur.fetchall()

                for source_id, orig_name, eid, ename, state, sim in rows:
                    sim_f = float(sim)
                    band = self._band_for_score(sim_f)
                    results.append(self._make_result(
                        source_id, eid, "FUZZY_TRIGRAM", "probabilistic", band, sim_f,
                        {"source_name": orig_name, "target_name": ename,
                         "state": state, "similarity": round(sim_f, 3)}
                    ))

                done = min(batch_start + batch_size, len(prepped))
                if done % 2000 == 0 or done == len(prepped):
                    print(f"    Fuzzy: {done:,}/{len(prepped):,} -- "
                          f"{len(results):,} matches")

        return results

    def _band_for_score(self, score: float) -> str:
        """Map score to confidence band."""
        if score >= self.HIGH_THRESHOLD:
            return "HIGH"
        if score >= self.MEDIUM_THRESHOLD:
            return "MEDIUM"
        return "LOW"

    def _record_match(self, result: Dict):
        """Update stats for a match."""
        self.stats["matched"] += 1
        method = result["method"]
        self.stats["by_method"][method] = self.stats["by_method"].get(method, 0) + 1
        self.stats["by_band"][result["band"]] += 1

    def _make_result(self, source_id, target_id, method, tier, band, score, evidence):
        """Create result dict and queue for unified_match_log."""
        normalized_score = self._normalize_confidence_score(score)
        method = method.upper()  # normalize match_method to UPPER
        result = {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "method": method,
            "tier": tier,
            "band": band,
            "score": round(normalized_score, 3),
            "evidence": evidence,
        }

        # Queue for unified_match_log
        # LOW confidence matches are logged but marked rejected
        status = "rejected" if band == "LOW" else "active"
        self._log_buffer.append((
            self.run_id, self.source_system, str(source_id),
            "f7", str(target_id),
            method, tier, band, normalized_score,
            json.dumps(evidence), status,
        ))

        # Flush periodically
        if len(self._log_buffer) >= 1000:
            self._flush_log()

        return result

    def _normalize_confidence_score(self, score: float) -> float:
        """
        Normalize confidence scores to 0.0-1.0.

        NLRB historical runs wrote 0-100 integers (e.g., 90, 98). Normalize
        those to decimals to keep cross-source confidence semantics consistent.
        """
        score_val = float(score)
        if self.source_system == "nlrb" and score_val > 1.0:
            score_val = score_val / 100.0
        return score_val

    def _flush_log(self):
        """Write buffered matches to unified_match_log."""
        if not self._log_buffer or self.dry_run:
            return

        from psycopg2.extras import execute_batch
        sql = """
            INSERT INTO unified_match_log
                (run_id, source_system, source_id, target_system, target_id,
                 match_method, match_tier, confidence_band, confidence_score,
                 evidence, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (run_id, source_system, source_id, target_id) DO NOTHING
        """
        with self.conn.cursor() as cur:
            execute_batch(cur, sql, self._log_buffer, page_size=1000)
        self.conn.commit()
        self._log_buffer.clear()

    def print_stats(self):
        """Print matching statistics."""
        total = self.stats["total"]
        matched = self.stats["matched"]
        rate = (matched / total * 100) if total > 0 else 0
        print(f"\n  Total: {total:,}, Matched: {matched:,} ({rate:.1f}%)")
        print(f"  By confidence: HIGH={self.stats['by_band']['HIGH']:,}, "
              f"MEDIUM={self.stats['by_band']['MEDIUM']:,}, "
              f"LOW={self.stats['by_band']['LOW']:,}")
        if self.stats["collisions_resolved"] or self.stats["collisions_ambiguous"]:
            print(f"  Collisions: {self.stats['collisions_resolved']:,} resolved by city, "
                  f"{self.stats['collisions_ambiguous']:,} ambiguous")
        if self.stats["by_method"]:
            print("  By method:")
            for method, count in sorted(self.stats["by_method"].items(),
                                        key=lambda x: -x[1]):
                print(f"    {method:40s} {count:>8,}")
