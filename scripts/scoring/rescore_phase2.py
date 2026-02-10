"""
Phase 2: Scorecard Quick Wins - Batch Re-Score All Targets

Updates score_geographic, score_size, and score_osha_violations on mergent_employers
using the Phase 2 improved methodology:
  - Geographic: RTW penalty + NLRB win rate + state union density
  - Size: Refined sweet spot (50-250 employees)
  - OSHA: Violations normalized to industry average

Then recalculates organizing_score and updates priority tiers.

Run: py scripts/scoring/rescore_phase2.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection
import psycopg2.extras


def main():
    conn = get_connection(cursor_factory=psycopg2.extras.RealDictCursor)
    cur = conn.cursor()

    print("=" * 70)
    print("PHASE 2: SCORECARD QUICK WINS - BATCH RE-SCORE")
    print("=" * 70)

    # ============================================================
    # Step 1: BEFORE snapshot
    # ============================================================
    print("\n=== Step 1: BEFORE snapshot ===")
    cur.execute("""
        SELECT score_priority, COUNT(*) as cnt
        FROM mergent_employers WHERE has_union IS NOT TRUE
        GROUP BY score_priority
        ORDER BY CASE score_priority
            WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END
    """)
    before_tiers = {r['score_priority']: r['cnt'] for r in cur.fetchall()}
    print("Tier distribution (BEFORE):")
    for tier in ['TOP', 'HIGH', 'MEDIUM', 'LOW']:
        print(f"  {tier}: {before_tiers.get(tier, 0):,}")

    cur.execute("""
        CREATE TEMP TABLE _before AS
        SELECT duns, score_geographic, score_size, score_osha_violations, organizing_score
        FROM mergent_employers WHERE has_union IS NOT TRUE
    """)
    print(f"Captured {cur.rowcount:,} employer scores")

    # ============================================================
    # Step 2: Update score_geographic (max 15)
    # RTW penalty + NLRB win rate + state density
    # ============================================================
    print("\n=== Step 2: Updating score_geographic ===")
    cur.execute("""
        UPDATE mergent_employers me
        SET score_geographic =
            -- Non-RTW bonus (0 or 5)
            CASE WHEN EXISTS (SELECT 1 FROM ref_rtw_states r WHERE r.state = me.state) THEN 0 ELSE 5 END
            +
            -- NLRB win rate component (0-5)
            COALESCE((
                SELECT CASE
                    WHEN n.win_rate_pct >= 85 THEN 5
                    WHEN n.win_rate_pct >= 75 THEN 4
                    WHEN n.win_rate_pct >= 65 THEN 3
                    WHEN n.win_rate_pct >= 55 THEN 2
                    ELSE 1
                END
                FROM ref_nlrb_state_win_rates n WHERE n.state = me.state
            ), 2)
            +
            -- State density component (0-5)
            COALESCE((
                SELECT CASE
                    WHEN e.members_total > 1000000 THEN 5
                    WHEN e.members_total > 500000 THEN 4
                    WHEN e.members_total > 200000 THEN 3
                    WHEN e.members_total > 100000 THEN 2
                    ELSE 1
                END
                FROM epi_state_benchmarks e WHERE e.state = me.state
            ), 1)
        WHERE has_union IS NOT TRUE
    """)
    print(f"  Updated {cur.rowcount:,} employers")
    conn.commit()

    # ============================================================
    # Step 3: Update score_size (max 10)
    # Refined: 50-250 sweet spot
    # ============================================================
    print("\n=== Step 3: Updating score_size ===")
    cur.execute("""
        UPDATE mergent_employers
        SET score_size = CASE
            WHEN COALESCE(employees_site, ny990_employees, employees_all_sites, 0)
                BETWEEN 50 AND 250 THEN 10
            WHEN COALESCE(employees_site, ny990_employees, employees_all_sites, 0)
                BETWEEN 251 AND 500 THEN 8
            WHEN COALESCE(employees_site, ny990_employees, employees_all_sites, 0)
                BETWEEN 25 AND 49 THEN 6
            WHEN COALESCE(employees_site, ny990_employees, employees_all_sites, 0)
                BETWEEN 501 AND 1000 THEN 4
            ELSE 2
        END
        WHERE has_union IS NOT TRUE
    """)
    print(f"  Updated {cur.rowcount:,} employers")
    conn.commit()

    # ============================================================
    # Step 4: Update score_osha_violations (max 10)
    # Normalized to industry average
    # ============================================================
    print("\n=== Step 4: Updating score_osha_violations ===")
    cur.execute("""
        UPDATE mergent_employers me
        SET score_osha_violations =
            CASE
                WHEN COALESCE(me.osha_violation_count, 0) = 0 THEN 0
                ELSE
                    LEAST(10,
                        -- Base from ratio to industry average (0-7)
                        CASE
                            WHEN me.osha_violation_count::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 4) AND digit_level = 4),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 3.0 THEN 7
                            WHEN me.osha_violation_count::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 4) AND digit_level = 4),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 2.0 THEN 5
                            WHEN me.osha_violation_count::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 4) AND digit_level = 4),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 1.5 THEN 4
                            WHEN me.osha_violation_count::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 4) AND digit_level = 4),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_violations_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 1.0 THEN 3
                            ELSE 1
                        END
                        +
                        -- Penalty severity bonus (0-3): above-average penalties
                        CASE
                            WHEN COALESCE(me.osha_total_penalties, 0)::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_penalty_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_penalty_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 3.0 THEN 3
                            WHEN COALESCE(me.osha_total_penalties, 0)::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_penalty_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_penalty_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 2.0 THEN 2
                            WHEN COALESCE(me.osha_total_penalties, 0)::numeric / NULLIF(
                                COALESCE(
                                    (SELECT avg_penalty_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = LEFT(me.naics_primary, 2) AND digit_level = 2),
                                    (SELECT avg_penalty_per_estab FROM ref_osha_industry_averages
                                     WHERE naics_prefix = 'ALL')
                                ), 0) >= 1.0 THEN 1
                            ELSE 0
                        END
                    )
            END
        WHERE has_union IS NOT TRUE
    """)
    print(f"  Updated {cur.rowcount:,} employers")
    conn.commit()

    # ============================================================
    # Step 5: Recalculate organizing_score
    # ============================================================
    print("\n=== Step 5: Recalculating organizing_score ===")
    cur.execute("""
        UPDATE mergent_employers
        SET organizing_score =
            COALESCE(score_geographic, 0)
            + COALESCE(score_size, 0)
            + COALESCE(score_industry_density, 0)
            + COALESCE(score_nlrb_momentum, 0)
            + COALESCE(score_osha_violations, 0)
            + COALESCE(score_govt_contracts, 0)
            + COALESCE(sibling_union_bonus, 0)
            + COALESCE(score_labor_violations, 0)
        WHERE has_union IS NOT TRUE
    """)
    print(f"  Updated {cur.rowcount:,} employers")
    conn.commit()

    # ============================================================
    # Step 6: Update priority tiers
    # ============================================================
    print("\n=== Step 6: Updating priority tiers ===")
    cur.execute("""
        UPDATE mergent_employers
        SET score_priority = CASE
            WHEN organizing_score >= 30 THEN 'TOP'
            WHEN organizing_score >= 25 THEN 'HIGH'
            WHEN organizing_score >= 20 THEN 'MEDIUM'
            ELSE 'LOW'
        END
        WHERE has_union IS NOT TRUE
    """)
    print(f"  Updated {cur.rowcount:,} employers")
    conn.commit()

    # ============================================================
    # Step 7: AFTER stats and comparison
    # ============================================================
    print("\n=== Step 7: AFTER comparison ===")

    cur.execute("""
        SELECT score_priority, COUNT(*) as cnt
        FROM mergent_employers WHERE has_union IS NOT TRUE
        GROUP BY score_priority
        ORDER BY CASE score_priority
            WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 ELSE 5 END
    """)
    after_tiers = {r['score_priority']: r['cnt'] for r in cur.fetchall()}

    print("\nTier distribution:")
    print(f"  {'Tier':<10} {'Before':>10} {'After':>10} {'Change':>10}")
    print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
    for tier in ['TOP', 'HIGH', 'MEDIUM', 'LOW']:
        before = before_tiers.get(tier, 0)
        after = after_tiers.get(tier, 0)
        change = after - before
        sign = '+' if change > 0 else ''
        print(f"  {tier:<10} {before:>10,} {after:>10,} {sign}{change:>9,}")

    # Component changes
    for col_name, label in [
        ('score_geographic', 'Geographic'),
        ('score_size', 'Size'),
        ('score_osha_violations', 'OSHA')
    ]:
        cur.execute(f"""
            SELECT
                COUNT(*) FILTER (WHERE m.{col_name} > COALESCE(b.{col_name}, 0)) as increased,
                COUNT(*) FILTER (WHERE m.{col_name} < COALESCE(b.{col_name}, 0)) as decreased,
                COUNT(*) FILTER (WHERE m.{col_name} IS DISTINCT FROM b.{col_name}) as changed,
                ROUND(AVG(m.{col_name})::numeric, 2) as new_avg,
                ROUND(AVG(b.{col_name})::numeric, 2) as old_avg
            FROM mergent_employers m
            JOIN _before b ON m.duns = b.duns
        """)
        r = cur.fetchone()
        print(f"\n  {label}: {r['changed']:,} changed ({r['increased']:,} up, {r['decreased']:,} down)")
        print(f"    Avg: {r['old_avg']} -> {r['new_avg']}")

    # Overall organizing_score change
    cur.execute("""
        SELECT
            COUNT(*) FILTER (WHERE m.organizing_score > COALESCE(b.organizing_score, 0)) as increased,
            COUNT(*) FILTER (WHERE m.organizing_score < COALESCE(b.organizing_score, 0)) as decreased,
            ROUND(AVG(m.organizing_score)::numeric, 2) as new_avg,
            ROUND(AVG(b.organizing_score)::numeric, 2) as old_avg
        FROM mergent_employers m
        JOIN _before b ON m.duns = b.duns
    """)
    r = cur.fetchone()
    print(f"\n  Overall Score: {r['increased']:,} increased, {r['decreased']:,} decreased")
    print(f"    Avg: {r['old_avg']} -> {r['new_avg']}")

    # Top 10 by new organizing_score
    print("\nTop 10 organizing targets (after re-score):")
    cur.execute("""
        SELECT company_name, state, organizing_score, score_priority,
               score_geographic, score_size, score_osha_violations,
               score_industry_density, score_nlrb_momentum,
               score_govt_contracts, score_labor_violations
        FROM mergent_employers
        WHERE has_union IS NOT TRUE
        ORDER BY organizing_score DESC
        LIMIT 10
    """)
    rows = cur.fetchall()
    print(f"  {'Employer':<35} {'ST':>2} {'Score':>5} {'Tier':<6} {'Geo':>3} {'Sz':>3} {'OSHA':>4} {'Ind':>3} {'NLRB':>4} {'Gov':>3} {'Lab':>3}")
    for r in rows:
        name = (r['company_name'] or '')[:35]
        print(f"  {name:<35} {r['state'] or '':>2} {r['organizing_score'] or 0:>5} "
              f"{r['score_priority'] or ''::<6} {r['score_geographic'] or 0:>3} "
              f"{r['score_size'] or 0:>3} {r['score_osha_violations'] or 0:>4} "
              f"{r['score_industry_density'] or 0:>3} {r['score_nlrb_momentum'] or 0:>4} "
              f"{r['score_govt_contracts'] or 0:>3} {r['score_labor_violations'] or 0:>3}")

    cur.execute("DROP TABLE IF EXISTS _before")
    conn.commit()
    cur.close()
    conn.close()

    print("\n" + "=" * 70)
    print("PHASE 2 RE-SCORE COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
