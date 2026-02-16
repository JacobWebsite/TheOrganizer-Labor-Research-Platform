"""
Backfill unified_match_log from existing match tables.

Maps method names to tier/confidence_band:
  - EXACT_*, EIN_* -> deterministic / HIGH
  - NORMALIZED_*, NAME_*_STATE -> deterministic / MEDIUM
  - FUZZY_*, TRIGRAM_* -> probabilistic / LOW or MEDIUM
  - ADDRESS_* -> deterministic / MEDIUM

Generates synthetic run_ids for historical data, builds evidence JSON.

Usage:
    py scripts/matching/backfill_unified_match_log.py
    py scripts/matching/backfill_unified_match_log.py --dry-run
"""
import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from db_config import get_connection


# ============================================================================
# Method -> tier/confidence mapping
# ============================================================================

METHOD_MAPPING = {
    # OSHA methods (24 distinct)
    "EXACT_NAME": ("deterministic", "HIGH", 0.95),
    "EXACT_EIN": ("deterministic", "HIGH", 1.0),
    "NORMALIZED": ("deterministic", "MEDIUM", 0.85),
    "AGGRESSIVE": ("deterministic", "MEDIUM", 0.75),
    "FUZZY": ("probabilistic", "LOW", 0.60),
    "ADDRESS": ("deterministic", "MEDIUM", 0.80),
    "FACILITY_STRIPPED": ("deterministic", "MEDIUM", 0.70),

    # WHD methods
    "NAME_CITY_STATE": ("deterministic", "HIGH", 0.90),
    "NAME_STATE": ("deterministic", "MEDIUM", 0.80),
    "TRADE_NAME": ("deterministic", "MEDIUM", 0.75),
    "MERGENT_BRIDGE": ("deterministic", "MEDIUM", 0.80),

    # 990 methods
    "EIN_CROSSWALK": ("deterministic", "HIGH", 0.95),
    "EIN_MERGENT": ("deterministic", "HIGH", 0.95),
    "EXACT_NAME_STATE": ("deterministic", "HIGH", 0.90),

    # Crosswalk methods
    "EIN_EXACT": ("deterministic", "HIGH", 1.0),
    "LEI_EXACT": ("deterministic", "HIGH", 1.0),
    "NAME_STATE": ("deterministic", "MEDIUM", 0.80),
    "SPLINK": ("probabilistic", "MEDIUM", 0.80),
}

# Fallback mapping by prefix
PREFIX_MAPPING = {
    "EIN": ("deterministic", "HIGH", 0.95),
    "EXACT": ("deterministic", "HIGH", 0.90),
    "NAME": ("deterministic", "MEDIUM", 0.80),
    "NORMALIZED": ("deterministic", "MEDIUM", 0.85),
    "AGGRESSIVE": ("deterministic", "MEDIUM", 0.75),
    "FUZZY": ("probabilistic", "LOW", 0.60),
    "TRIGRAM": ("probabilistic", "LOW", 0.60),
    "ADDRESS": ("deterministic", "MEDIUM", 0.80),
    "SPLINK": ("probabilistic", "MEDIUM", 0.80),
    "TRADE": ("deterministic", "MEDIUM", 0.75),
    "MERGENT": ("deterministic", "MEDIUM", 0.80),
}


def classify_method(method, confidence_score=None):
    """Map a match method string to (tier, confidence_band, default_score)."""
    if not method:
        return ("deterministic", "LOW", 0.50)

    method_upper = method.upper().strip()

    # Exact lookup
    if method_upper in METHOD_MAPPING:
        tier, band, default_score = METHOD_MAPPING[method_upper]
        return (tier, band, confidence_score if confidence_score is not None else default_score)

    # Prefix-based fallback
    for prefix, (tier, band, default_score) in PREFIX_MAPPING.items():
        if method_upper.startswith(prefix):
            return (tier, band, confidence_score if confidence_score is not None else default_score)

    # Unknown method
    return ("deterministic", "LOW", confidence_score if confidence_score is not None else 0.50)


def backfill_osha(conn, run_id, dry_run=False):
    """Backfill from osha_f7_matches."""
    print("\n--- OSHA matches ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT establishment_id, f7_employer_id, match_method,
                   match_confidence, created_at
            FROM osha_f7_matches
        """)
        rows = cur.fetchall()
        print(f"  Found {len(rows)} OSHA matches")

        if dry_run:
            _summarize(rows, 2)
            return len(rows)

        batch = []
        for r in rows:
            tier, band, score = classify_method(
                r[2], float(r[3]) if r[3] is not None else None
            )
            evidence = {
                "source_table": "osha_f7_matches",
                "establishment_id": r[0],
                "original_method": r[2],
                "original_confidence": float(r[3]) if r[3] is not None else None,
            }
            batch.append((
                run_id, "osha", str(r[0]), "f7", str(r[1]),
                r[2] or "UNKNOWN", tier, band, score,
                json.dumps(evidence), "active",
            ))

        _insert_batch(cur, batch)
        conn.commit()
        print(f"  Inserted {len(batch)} OSHA rows")
        return len(batch)


def backfill_whd(conn, run_id, dry_run=False):
    """Backfill from whd_f7_matches."""
    print("\n--- WHD matches ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT case_id, f7_employer_id, match_method,
                   match_confidence, match_source, created_at
            FROM whd_f7_matches
        """)
        rows = cur.fetchall()
        print(f"  Found {len(rows)} WHD matches")

        if dry_run:
            _summarize(rows, 2)
            return len(rows)

        batch = []
        for r in rows:
            tier, band, score = classify_method(
                r[2], float(r[3]) if r[3] is not None else None
            )
            evidence = {
                "source_table": "whd_f7_matches",
                "case_id": r[0],
                "original_method": r[2],
                "original_confidence": float(r[3]) if r[3] is not None else None,
                "match_source": r[4],
            }
            batch.append((
                run_id, "whd", str(r[0]), "f7", str(r[1]),
                r[2] or "UNKNOWN", tier, band, score,
                json.dumps(evidence), "active",
            ))

        _insert_batch(cur, batch)
        conn.commit()
        print(f"  Inserted {len(batch)} WHD rows")
        return len(batch)


def backfill_990(conn, run_id, dry_run=False):
    """Backfill from national_990_f7_matches."""
    print("\n--- 990 matches ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT n990_id, f7_employer_id, match_method,
                   match_confidence, ein, match_source, created_at
            FROM national_990_f7_matches
        """)
        rows = cur.fetchall()
        print(f"  Found {len(rows)} 990 matches")

        if dry_run:
            _summarize(rows, 2)
            return len(rows)

        batch = []
        for r in rows:
            tier, band, score = classify_method(
                r[2], float(r[3]) if r[3] is not None else None
            )
            evidence = {
                "source_table": "national_990_f7_matches",
                "n990_id": r[0],
                "ein": r[4],
                "original_method": r[2],
                "original_confidence": float(r[3]) if r[3] is not None else None,
                "match_source": r[5],
            }
            batch.append((
                run_id, "990", str(r[0]), "f7", str(r[1]),
                r[2] or "UNKNOWN", tier, band, score,
                json.dumps(evidence), "active",
            ))

        _insert_batch(cur, batch)
        conn.commit()
        print(f"  Inserted {len(batch)} 990 rows")
        return len(batch)


def backfill_sam(conn, run_id, dry_run=False):
    """Backfill from sam_f7_matches."""
    print("\n--- SAM matches ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT uei, f7_employer_id, match_method,
                   match_confidence, match_source, created_at
            FROM sam_f7_matches
        """)
        rows = cur.fetchall()
        print(f"  Found {len(rows)} SAM matches")

        if dry_run:
            _summarize(rows, 2)
            return len(rows)

        batch = []
        for r in rows:
            tier, band, score = classify_method(
                r[2], float(r[3]) if r[3] is not None else None
            )
            evidence = {
                "source_table": "sam_f7_matches",
                "uei": r[0],
                "original_method": r[2],
                "original_confidence": float(r[3]) if r[3] is not None else None,
                "match_source": r[4],
            }
            batch.append((
                run_id, "sam", str(r[0]), "f7", str(r[1]),
                r[2] or "UNKNOWN", tier, band, score,
                json.dumps(evidence), "active",
            ))

        _insert_batch(cur, batch)
        conn.commit()
        print(f"  Inserted {len(batch)} SAM rows")
        return len(batch)


def backfill_nlrb(conn, run_id, dry_run=False):
    """Backfill from nlrb_employer_xref."""
    print("\n--- NLRB matches ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT xref_id, nlrb_employer_name, nlrb_city, nlrb_state,
                   f7_employer_id,
                   match_confidence, match_method
            FROM nlrb_employer_xref
            WHERE f7_employer_id IS NOT NULL
        """)
        rows = cur.fetchall()
        print(f"  Found {len(rows)} NLRB matches")

        if dry_run:
            _summarize(rows, 6)
            return len(rows)

        batch = []
        for r in rows:
            tier, band, score = classify_method(
                r[6], float(r[5]) if r[5] is not None else None
            )
            evidence = {
                "source_table": "nlrb_employer_xref",
                "xref_id": r[0],
                "nlrb_employer_name": r[1],
                "nlrb_city": r[2],
                "nlrb_state": r[3],
                "original_method": r[6],
                "original_confidence": float(r[5]) if r[5] is not None else None,
            }
            batch.append((
                run_id, "nlrb", str(r[0]), "f7", str(r[4]),
                r[6] or "UNKNOWN", tier, band, score,
                json.dumps(evidence), "active",
            ))

        _insert_batch(cur, batch)
        conn.commit()
        print(f"  Inserted {len(batch)} NLRB rows")
        return len(batch)


def backfill_crosswalk(conn, run_id, dry_run=False):
    """Backfill from corporate_identifier_crosswalk for non-F7 links."""
    print("\n--- Crosswalk matches ---")
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, f7_employer_id, match_tier, match_confidence,
                   ein, sec_cik, gleif_lei, mergent_duns,
                   canonical_name, state, sec_id, gleif_id,
                   is_federal_contractor
            FROM corporate_identifier_crosswalk
            WHERE f7_employer_id IS NOT NULL
        """)
        rows = cur.fetchall()
        print(f"  Found {len(rows)} crosswalk links")

        if dry_run:
            _summarize(rows, 2)
            return len(rows)

        batch = []
        for r in rows:
            # Determine source_system from which IDs are populated
            if r[7]:  # mergent_duns
                source_system = "mergent"
            elif r[6]:  # gleif_lei
                source_system = "gleif"
            elif r[5] or r[10]:  # sec_cik or sec_id
                source_system = "sec"
            elif r[4]:  # ein
                source_system = "crosswalk"
            else:
                source_system = "crosswalk"

            # match_tier -> confidence mapping
            tier_str = (r[2] or "").upper()
            conf_str = (r[3] or "MEDIUM").upper()

            if conf_str == "HIGH" or tier_str in ("EIN_EXACT", "LEI_EXACT", "EXACT"):
                band, score = "HIGH", 0.95
            elif conf_str == "LOW":
                band, score = "LOW", 0.50
            else:
                band, score = "MEDIUM", 0.80

            match_tier = "deterministic"
            method = r[2] or "CROSSWALK"
            if "SPLINK" in method.upper() or "PROBABILISTIC" in method.upper():
                match_tier = "probabilistic"

            evidence = {
                "source_table": "corporate_identifier_crosswalk",
                "crosswalk_id": r[0],
                "ein": r[4],
                "sec_cik": r[5],
                "gleif_lei": r[6],
                "mergent_duns": r[7],
                "canonical_name": r[8],
                "state": r[9],
                "original_match_tier": r[2],
                "original_confidence": r[3],
                "is_federal_contractor": r[12],
            }

            # source_id: use the most specific identifier
            source_id = str(r[0])  # fallback to crosswalk id
            if r[7]:  # mergent_duns
                source_id = str(r[7])
            elif r[6]:  # gleif_lei
                source_id = str(r[6])
            elif r[5]:  # sec_cik
                source_id = str(r[5])
            elif r[4]:  # ein
                source_id = str(r[4])

            batch.append((
                run_id, source_system, source_id, "f7", str(r[1]),
                method, match_tier, band, score,
                json.dumps(evidence), "active",
            ))

        _insert_batch(cur, batch)
        conn.commit()
        print(f"  Inserted {len(batch)} crosswalk rows")
        return len(batch)


def _insert_batch(cur, batch, batch_size=5000):
    """Insert batch rows with ON CONFLICT skip."""
    sql = """
        INSERT INTO unified_match_log
            (run_id, source_system, source_id, target_system, target_id,
             match_method, match_tier, confidence_band, confidence_score,
             evidence, status)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (run_id, source_system, source_id, target_id) DO NOTHING
    """
    for i in range(0, len(batch), batch_size):
        chunk = batch[i:i + batch_size]
        from psycopg2.extras import execute_batch
        execute_batch(cur, sql, chunk, page_size=1000)


def _summarize(rows, method_col_idx):
    """Print method distribution for dry-run."""
    from collections import Counter
    methods = Counter(r[method_col_idx] for r in rows)
    for method, count in methods.most_common():
        tier, band, score = classify_method(method)
        method_str = method or "NULL"
        print(f"    {method_str:30s} -> {tier:15s} {band:8s} ({count:,} rows)")


def main():
    parser = argparse.ArgumentParser(description="Backfill unified_match_log")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be inserted")
    parser.add_argument("--source", choices=["osha", "whd", "990", "sam", "nlrb", "crosswalk", "all"],
                        default="all", help="Which source to backfill")
    args = parser.parse_args()

    conn = get_connection()
    try:
        # Generate a single backfill run_id
        run_id = f"backfill-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        print(f"Backfill run_id: {run_id}")

        if not args.dry_run:
            # Register in match_runs
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO match_runs (run_id, scenario, started_at, source_system, method_type)
                    VALUES (%s, %s, NOW(), %s, %s)
                    ON CONFLICT (run_id) DO NOTHING
                """, [run_id, "backfill_unified", "all", "backfill"])
                conn.commit()

        sources = {
            "osha": backfill_osha,
            "whd": backfill_whd,
            "990": backfill_990,
            "sam": backfill_sam,
            "nlrb": backfill_nlrb,
            "crosswalk": backfill_crosswalk,
        }

        total = 0
        if args.source == "all":
            for name, func in sources.items():
                total += func(conn, run_id, args.dry_run)
        else:
            total = sources[args.source](conn, run_id, args.dry_run)

        if not args.dry_run:
            # Update match_runs with final counts
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE match_runs
                    SET completed_at = NOW(),
                        total_matched = %s
                    WHERE run_id = %s
                """, [total, run_id])

                # Update confidence counts
                cur.execute("""
                    UPDATE match_runs mr SET
                        high_count = sub.high,
                        medium_count = sub.medium,
                        low_count = sub.low
                    FROM (
                        SELECT
                            COUNT(*) FILTER (WHERE confidence_band = 'HIGH') as high,
                            COUNT(*) FILTER (WHERE confidence_band = 'MEDIUM') as medium,
                            COUNT(*) FILTER (WHERE confidence_band = 'LOW') as low
                        FROM unified_match_log
                        WHERE run_id = %s
                    ) sub
                    WHERE mr.run_id = %s
                """, [run_id, run_id])
                conn.commit()

        print(f"\n{'[DRY RUN] Would insert' if args.dry_run else 'Total inserted'}: {total:,} rows")

        if not args.dry_run:
            # Final summary
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT source_system, confidence_band, COUNT(*)
                    FROM unified_match_log
                    WHERE run_id = %s
                    GROUP BY source_system, confidence_band
                    ORDER BY source_system, confidence_band
                """, [run_id])
                print("\nSummary by source_system + confidence:")
                for row in cur.fetchall():
                    print(f"  {row[0]:12s} {row[1]:8s} {row[2]:>8,}")

                cur.execute("SELECT COUNT(*) FROM unified_match_log")
                print(f"\nTotal unified_match_log rows: {cur.fetchone()[0]:,}")

    finally:
        conn.close()


if __name__ == "__main__":
    main()
