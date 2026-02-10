import os
"""
Update labor violation scores using national WHD data + NYC Comptroller data,
recalculate organizing scores, and refresh views.

Prerequisites: WHD data already matched to mergent_employers and f7_employers_deduped
               (by match_whd_to_employers.py)
"""
import psycopg2
import subprocess

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

print("=" * 70)
print("UPDATE LABOR VIOLATION SCORES WITH NATIONAL WHD DATA")
print("=" * 70)

# ============================================================
# Step 1: BEFORE stats - capture current state for comparison
# ============================================================
print("\n=== Step 1: BEFORE stats ===")

# Score distribution
cur.execute("""
    SELECT score_labor_violations, COUNT(*)
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
    GROUP BY score_labor_violations
    ORDER BY score_labor_violations
""")
before_score_dist = {r[0]: r[1] for r in cur.fetchall()}
print("\nScore distribution (BEFORE):")
for score in sorted(before_score_dist.keys()):
    label = score if score is not None else 'NULL'
    print(f"  {label} pts: {before_score_dist[score]:,} employers")

# Tier distribution
cur.execute("""
    SELECT score_priority, COUNT(*)
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
    GROUP BY score_priority
    ORDER BY CASE score_priority
        WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4
        ELSE 5 END
""")
before_tier_dist = {r[0]: r[1] for r in cur.fetchall()}
print("\nTier distribution (BEFORE):")
for tier, count in before_tier_dist.items():
    print(f"  {tier}: {count:,}")

# Snapshot current scores for comparison
cur.execute("""
    CREATE TEMP TABLE _before_scores AS
    SELECT duns, score_labor_violations, organizing_score
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
""")
print(f"\nCaptured {cur.rowcount:,} employer scores for comparison")

# WHD data coverage check
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE whd_violation_count > 0) as with_whd_violations,
        COUNT(*) FILTER (WHERE whd_backwages > 0) as with_whd_backwages,
        SUM(COALESCE(whd_backwages, 0)) as total_whd_backwages,
        COUNT(*) FILTER (WHERE nyc_wage_theft_cases > 0) as with_nyc_wage_theft,
        SUM(COALESCE(nyc_wage_theft_amount, 0)) as total_nyc_wage_theft
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
""")
r = cur.fetchone()
print(f"\nWHD data coverage (non-union targets):")
print(f"  Employers with WHD violations: {r[0]:,}")
print(f"  Employers with WHD backwages:  {r[1]:,}")
print(f"  Total WHD backwages:           ${r[2]:,.2f}" if r[2] else "  Total WHD backwages:           $0.00")
print(f"  Employers with NYC wage theft: {r[3]:,}")
print(f"  Total NYC wage theft:          ${r[4]:,.2f}" if r[4] else "  Total NYC wage theft:          $0.00")

# ============================================================
# Step 2: Update score_labor_violations (0-10 pts)
#   - Wage theft: WHD national + NYC Comptroller (0-4 pts)
#   - ULP cases: NYC only (0-3 pts)
#   - Local labor law: NYC only (0-2 pts)
#   - Debarment: NYC only (0-1 pt)
# ============================================================
print("\n=== Step 2: Updating score_labor_violations ===")
cur.execute("""
    UPDATE mergent_employers
    SET score_labor_violations =
        -- Wage theft from WHD national + NYC Comptroller (0-4 pts)
        CASE
            WHEN COALESCE(whd_backwages, 0) + COALESCE(nyc_wage_theft_amount, 0) >= 100000 THEN 4
            WHEN COALESCE(whd_backwages, 0) + COALESCE(nyc_wage_theft_amount, 0) >= 50000 THEN 3
            WHEN COALESCE(whd_backwages, 0) + COALESCE(nyc_wage_theft_amount, 0) >= 10000 THEN 2
            WHEN COALESCE(whd_violation_count, 0) + COALESCE(nyc_wage_theft_cases, 0) > 0 THEN 1
            ELSE 0
        END
        +
        -- ULP cases (0-3 pts) - NYC only, unchanged
        CASE
            WHEN COALESCE(nyc_ulp_cases, 0) >= 3 THEN 3
            WHEN COALESCE(nyc_ulp_cases, 0) >= 2 THEN 2
            WHEN COALESCE(nyc_ulp_cases, 0) >= 1 THEN 1
            ELSE 0
        END
        +
        -- Local labor law (0-2 pts) - NYC only, unchanged
        CASE
            WHEN COALESCE(nyc_local_law_cases, 0) >= 2 THEN 2
            WHEN COALESCE(nyc_local_law_cases, 0) >= 1 THEN 1
            ELSE 0
        END
        +
        -- Debarment (0-1 pt) - NYC only, unchanged
        CASE WHEN nyc_debarred THEN 1 ELSE 0 END
    WHERE has_union IS NOT TRUE
""")
print(f"  Updated score_labor_violations for {cur.rowcount:,} employers")
conn.commit()

# ============================================================
# Step 3: Recalculate organizing_score
# ============================================================
print("\n=== Step 3: Recalculating organizing_score ===")
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
print(f"  Updated organizing_score for {cur.rowcount:,} employers")
conn.commit()

# ============================================================
# Step 4: Update score_priority tiers
# ============================================================
print("\n=== Step 4: Updating score_priority tiers ===")
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
print(f"  Updated score_priority for {cur.rowcount:,} employers")
conn.commit()

# ============================================================
# Step 5: Refresh sector views
# ============================================================
print("\n=== Step 5: Refreshing sector views ===")
result = subprocess.run(
    ['py', 'scripts/scoring/create_sector_views.py'],
    capture_output=True, text=True,
    cwd=r'C:\Users\jakew\Downloads\labor-data-project'
)
print(result.stdout)
if result.returncode != 0:
    print("WARNING: Sector view refresh failed:", result.stderr)

# ============================================================
# Step 6: Refresh materialized views
# ============================================================
print("\n=== Step 6: Refreshing materialized views ===")
cur.execute("REFRESH MATERIALIZED VIEW mv_employer_search")
conn.commit()
print("  Refreshed mv_employer_search")

# ============================================================
# Step 7: AFTER stats and comparison
# ============================================================
print("\n=== Step 7: AFTER stats ===")

# New score distribution
cur.execute("""
    SELECT score_labor_violations, COUNT(*)
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
    GROUP BY score_labor_violations
    ORDER BY score_labor_violations
""")
after_score_dist = {r[0]: r[1] for r in cur.fetchall()}
print("\nScore distribution (AFTER):")
print(f"  {'Score':<8} {'Before':>10} {'After':>10} {'Change':>10}")
print(f"  {'-'*8} {'-'*10} {'-'*10} {'-'*10}")
all_scores = sorted(set(list(before_score_dist.keys()) + list(after_score_dist.keys())),
                    key=lambda x: (x is None, x))
for score in all_scores:
    label = str(score) if score is not None else 'NULL'
    before = before_score_dist.get(score, 0)
    after = after_score_dist.get(score, 0)
    change = after - before
    sign = '+' if change > 0 else ''
    print(f"  {label:<8} {before:>10,} {after:>10,} {sign}{change:>9,}")

# New tier distribution
cur.execute("""
    SELECT score_priority, COUNT(*)
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
    GROUP BY score_priority
    ORDER BY CASE score_priority
        WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4
        ELSE 5 END
""")
after_tier_dist = {r[0]: r[1] for r in cur.fetchall()}
print("\nTier distribution (AFTER):")
print(f"  {'Tier':<10} {'Before':>10} {'After':>10} {'Change':>10}")
print(f"  {'-'*10} {'-'*10} {'-'*10} {'-'*10}")
all_tiers = ['TOP', 'HIGH', 'MEDIUM', 'LOW']
for tier in all_tiers:
    before = before_tier_dist.get(tier, 0)
    after = after_tier_dist.get(tier, 0)
    change = after - before
    sign = '+' if change > 0 else ''
    print(f"  {tier:<10} {before:>10,} {after:>10,} {sign}{change:>9,}")

# Count employers whose score_labor_violations increased
cur.execute("""
    SELECT COUNT(*)
    FROM mergent_employers m
    JOIN _before_scores b ON m.duns = b.duns
    WHERE m.score_labor_violations > COALESCE(b.score_labor_violations, 0)
""")
increased_count = cur.fetchone()[0]
print(f"\nEmployers whose score_labor_violations INCREASED: {increased_count:,}")

# Count employers whose score_labor_violations decreased
cur.execute("""
    SELECT COUNT(*)
    FROM mergent_employers m
    JOIN _before_scores b ON m.duns = b.duns
    WHERE m.score_labor_violations < COALESCE(b.score_labor_violations, 0)
""")
decreased_count = cur.fetchone()[0]
print(f"Employers whose score_labor_violations DECREASED: {decreased_count:,}")

# Count employers whose organizing_score changed
cur.execute("""
    SELECT COUNT(*)
    FROM mergent_employers m
    JOIN _before_scores b ON m.duns = b.duns
    WHERE m.organizing_score IS DISTINCT FROM b.organizing_score
""")
score_changed_count = cur.fetchone()[0]
print(f"Employers whose organizing_score CHANGED:         {score_changed_count:,}")

# Top 10 employers with highest new score_labor_violations
print("\nTop 10 employers by score_labor_violations:")
cur.execute("""
    SELECT
        company_name,
        state,
        score_labor_violations,
        COALESCE(whd_violation_count, 0) as whd_violations,
        COALESCE(whd_backwages, 0) as whd_backwages,
        COALESCE(nyc_wage_theft_amount, 0) as nyc_wage_theft,
        COALESCE(nyc_ulp_cases, 0) as ulp_cases,
        COALESCE(nyc_local_law_cases, 0) as local_law,
        COALESCE(nyc_debarred, FALSE) as debarred,
        organizing_score,
        score_priority
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
      AND score_labor_violations > 0
    ORDER BY score_labor_violations DESC, organizing_score DESC
    LIMIT 10
""")
rows = cur.fetchall()
print(f"  {'Employer':<40} {'ST':<4} {'LV':>3} {'WHD#':>5} {'WHD$':>12} {'NYC$':>12} {'ULP':>4} {'LL':>3} {'Deb':>4} {'Score':>6} {'Tier':<6}")
print(f"  {'-'*40} {'-'*4} {'-'*3} {'-'*5} {'-'*12} {'-'*12} {'-'*4} {'-'*3} {'-'*4} {'-'*6} {'-'*6}")
for r in rows:
    name = (r[0] or '')[:40]
    st = r[1] or ''
    lv = r[2] or 0
    whd_n = r[3]
    whd_amt = r[4]
    nyc_amt = r[5]
    ulp = r[6]
    ll = r[7]
    deb = 'Y' if r[8] else 'N'
    org = r[9] or 0
    tier = r[10] or ''
    print(f"  {name:<40} {st:<4} {lv:>3} {whd_n:>5} ${whd_amt:>11,.2f} ${nyc_amt:>11,.2f} {ulp:>4} {ll:>3} {deb:>4} {org:>6} {tier:<6}")

# Breakdown: how many got points from WHD-only vs NYC-only vs both
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE COALESCE(whd_violation_count, 0) > 0 AND COALESCE(nyc_wage_theft_cases, 0) = 0)
            as whd_only,
        COUNT(*) FILTER (WHERE COALESCE(whd_violation_count, 0) = 0 AND COALESCE(nyc_wage_theft_cases, 0) > 0)
            as nyc_only,
        COUNT(*) FILTER (WHERE COALESCE(whd_violation_count, 0) > 0 AND COALESCE(nyc_wage_theft_cases, 0) > 0)
            as both_sources
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
      AND score_labor_violations > 0
""")
r = cur.fetchone()
print(f"\nWage theft source breakdown (among scored employers):")
print(f"  WHD national only: {r[0]:,}")
print(f"  NYC Comptroller only: {r[1]:,}")
print(f"  Both sources: {r[2]:,}")

# Cleanup temp table
cur.execute("DROP TABLE IF EXISTS _before_scores")
conn.commit()

cur.close()
conn.close()

print("\n" + "=" * 70)
print("WHD SCORE UPDATE COMPLETE")
print("=" * 70)
