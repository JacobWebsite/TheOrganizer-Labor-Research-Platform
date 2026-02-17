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
  5. Fuzzy trigram similarity >= 0.4 (confidence = similarity score)

Collision resolution order:
  - Single candidate: accept directly
  - City match narrows to 1: accept with CITY_RESOLVED suffix
  - Splink disambiguation: compare source against 2-10 candidates, pick winner
  - Still ambiguous: flag as AMBIGUOUS with LOW confidence

All matches are logged to unified_match_log.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
)

# Tier specificity ranking (higher = more specific = preferred)
TIER_RANK = {
    "EIN_EXACT": 100,
    "NAME_CITY_STATE_EXACT": 90,
    "NAME_STATE_EXACT": 80,
    "NAME_AGGRESSIVE_STATE": 60,
    "FUZZY_SPLINK_ADAPTIVE": 45,
    "FUZZY_TRIGRAM": 40,
}


class DeterministicMatcher:
    """Cascade deterministic matcher with best-match-wins logic."""
    HIGH_THRESHOLD = 0.85
    MEDIUM_THRESHOLD = 0.70

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
        self._log_buffer = []
        self._indexes_loaded = False

        # In-memory indexes: each key maps to LIST of (employer_id, employer_name, city)
        self._ein_idx = {}              # ein -> (employer_id, employer_name)
        self._name_state_idx = {}       # (name_standard, STATE) -> [(eid, ename, CITY), ...]
        self._name_city_state_idx = {}  # (name_standard, CITY, STATE) -> [(eid, ename), ...]
        self._agg_state_idx = {}        # (name_aggressive, STATE) -> [(eid, ename, CITY), ...]

    def _build_indexes(self):
        """Load F7 employers + crosswalk into in-memory lookup dicts."""
        if self._indexes_loaded:
            return

        print("  Building in-memory indexes...")

        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, name_standard, name_aggressive,
                       UPPER(COALESCE(state, '')), UPPER(COALESCE(city, ''))
                FROM f7_employers_deduped
                WHERE name_standard IS NOT NULL
            """)
            rows = cur.fetchall()

        collisions_ns = 0
        collisions_as = 0

        for eid, ename, nstd, nagg, st, ct in rows:
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

            # name_aggressive + state -> list of candidates
            if nagg:
                key_as = (nagg, st)
                if key_as not in self._agg_state_idx:
                    self._agg_state_idx[key_as] = []
                else:
                    collisions_as += 1
                self._agg_state_idx[key_as].append((eid, ename, ct))

        print(f"    name+state keys:      {len(self._name_state_idx):,} ({collisions_ns:,} collision adds)")
        print(f"    name+city+state keys:  {len(self._name_city_state_idx):,}")
        print(f"    aggressive+state keys: {len(self._agg_state_idx):,} ({collisions_as:,} collision adds)")

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

        Tier priority: EIN(100) > name+city+state(90) > name+state(80) > aggressive+state(60)
        Within a tier, city disambiguation resolves multi-candidate collisions.
        """
        source_id = str(rec["id"])
        name = rec.get("name") or ""
        state = (rec.get("state") or "").upper().strip()
        city = (rec.get("city") or "").upper().strip()
        ein = (rec.get("ein") or "").strip()

        name_std = normalize_name_standard(name)
        name_agg = normalize_name_aggressive(name)

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
                # Even name+city+state can have multiple candidates (same name, same city)
                # Pick first — these are very likely the same entity or close enough
                eid, ename = candidates[0]
                result = self._make_result(
                    source_id, eid, "NAME_CITY_STATE_EXACT", "deterministic", "HIGH", 0.95,
                    {"source_name": name, "target_name": ename, "city": city, "state": state}
                )
                new_rank = TIER_RANK["NAME_CITY_STATE_EXACT"]
                if best is None or new_rank > best[0]:
                    best = (new_rank, result)

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
        if name_agg and state and (best is None or best[0] < TIER_RANK["NAME_AGGRESSIVE_STATE"]):
            candidates = self._agg_state_idx.get((name_agg, state))
            if candidates:
                resolved = self._disambiguate(candidates, city, source_id, name, state,
                                               "NAME_AGGRESSIVE_STATE", 0.75,
                                               source_rec=rec)
                if resolved:
                    new_rank = TIER_RANK["NAME_AGGRESSIVE_STATE"]
                    if best is None or new_rank > best[0]:
                        best = (new_rank, resolved)

        return best[1] if best else None

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

    def _fuzzy_batch(self, records: List[Dict], batch_size: int = 200) -> List[Dict]:
        """Tier 5 fuzzy matching using pg_trgm."""
        return self._fuzzy_batch_trigram(records, batch_size=batch_size)

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
        result = {
            "source_id": str(source_id),
            "target_id": str(target_id),
            "method": method,
            "tier": tier,
            "band": band,
            "score": round(score, 3),
            "evidence": evidence,
        }

        # Queue for unified_match_log
        # LOW confidence matches are logged but marked rejected
        status = "rejected" if band == "LOW" else "active"
        self._log_buffer.append((
            self.run_id, self.source_system, str(source_id),
            "f7", str(target_id),
            method, tier, band, score,
            json.dumps(evidence), status,
        ))

        # Flush periodically
        if len(self._log_buffer) >= 1000:
            self._flush_log()

        return result

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

