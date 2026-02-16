"""
Deterministic Matching Engine v3 (batch-optimized).

Single entry point for cascade matching against f7_employers_deduped.
Uses in-memory indexes for tiers 1-5 (O(1) lookups) and batched SQL
for tier 6 (fuzzy trigram).

Cascade order:
  1. EIN exact match (when available)
  2. name_standard + state (exact)
  3. name_standard + city + state (exact)
  4. name_aggressive + state
  5. name_fuzzy + state (trigram similarity >= 0.4) -- batched SQL

All matches are logged to unified_match_log.
"""
import json
import sys
from pathlib import Path
from typing import Dict, List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection
from src.python.matching.name_normalization import (
    normalize_name_standard,
    normalize_name_aggressive,
)


class DeterministicMatcher:
    """Cascade deterministic matcher with in-memory indexes."""

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
        }
        self._log_buffer = []
        self._indexes_loaded = False

        # In-memory indexes (populated by _build_indexes)
        self._ein_idx = {}          # ein -> (employer_id, employer_name)
        self._name_state_idx = {}   # (name_standard, STATE) -> (employer_id, employer_name)
        self._name_city_state_idx = {}  # (name_standard, CITY, STATE) -> (employer_id, name)
        self._agg_state_idx = {}    # (name_aggressive, STATE) -> (employer_id, employer_name)

    def _build_indexes(self):
        """Load F7 employers + crosswalk into in-memory lookup dicts."""
        if self._indexes_loaded:
            return

        print("  Building in-memory indexes...")

        # Load F7 employers
        with self.conn.cursor() as cur:
            cur.execute("""
                SELECT employer_id, employer_name, name_standard, name_aggressive,
                       UPPER(COALESCE(state, '')), UPPER(COALESCE(city, ''))
                FROM f7_employers_deduped
                WHERE name_standard IS NOT NULL
            """)
            rows = cur.fetchall()

        for eid, ename, nstd, nagg, st, ct in rows:
            key_ns = (nstd, st)
            if key_ns not in self._name_state_idx:
                self._name_state_idx[key_ns] = (eid, ename)

            if ct:
                key_ncs = (nstd, ct, st)
                if key_ncs not in self._name_city_state_idx:
                    self._name_city_state_idx[key_ncs] = (eid, ename)

            if nagg:
                key_as = (nagg, st)
                if key_as not in self._agg_state_idx:
                    self._agg_state_idx[key_as] = (eid, ename)

        print(f"    name+state keys:      {len(self._name_state_idx):,}")
        print(f"    name+city+state keys:  {len(self._name_city_state_idx):,}")
        print(f"    aggressive+state keys: {len(self._agg_state_idx):,}")

        # Load EIN index from crosswalk
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
        unmatched = []  # Records that need fuzzy matching
        self.stats["total"] += len(records)

        # Pass 1: In-memory exact matching (tiers 1-4)
        for i, rec in enumerate(records):
            result = self._match_exact(rec)
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

    def _match_exact(self, rec: Dict) -> Optional[Dict]:
        """Try tiers 1-4 using in-memory indexes."""
        source_id = str(rec["id"])
        name = rec.get("name") or ""
        state = (rec.get("state") or "").upper().strip()
        city = (rec.get("city") or "").upper().strip()
        ein = (rec.get("ein") or "").strip()

        name_std = normalize_name_standard(name)
        name_agg = normalize_name_aggressive(name)

        # Tier 1: EIN exact match
        if ein and len(ein) >= 8:
            fid = self._ein_idx.get(ein)
            if fid:
                return self._make_result(
                    source_id, fid, "EIN_EXACT", "deterministic", "HIGH", 1.0,
                    {"ein": ein, "source_name": name}
                )

        # Tier 2: name_standard + state
        if name_std and state:
            hit = self._name_state_idx.get((name_std, state))
            if hit:
                return self._make_result(
                    source_id, hit[0], "NAME_STATE_EXACT", "deterministic", "HIGH", 0.90,
                    {"source_name": name, "target_name": hit[1], "state": state}
                )

        # Tier 3: name_standard + city + state
        if name_std and city and state:
            hit = self._name_city_state_idx.get((name_std, city, state))
            if hit:
                return self._make_result(
                    source_id, hit[0], "NAME_CITY_STATE_EXACT", "deterministic", "HIGH", 0.92,
                    {"source_name": name, "target_name": hit[1], "city": city, "state": state}
                )

        # Tier 4: name_aggressive + state
        if name_agg and state:
            hit = self._agg_state_idx.get((name_agg, state))
            if hit:
                return self._make_result(
                    source_id, hit[0], "NAME_AGGRESSIVE_STATE", "deterministic", "MEDIUM", 0.75,
                    {"source_name": name, "target_name": hit[1], "state": state}
                )

        return None

    def _fuzzy_batch(self, records: List[Dict], batch_size: int = 200) -> List[Dict]:
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
                    band = "MEDIUM" if sim_f >= 0.6 else "LOW"
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
        if self.stats["by_method"]:
            print("  By method:")
            for method, count in sorted(self.stats["by_method"].items(),
                                        key=lambda x: -x[1]):
                print(f"    {method:30s} {count:>8,}")
