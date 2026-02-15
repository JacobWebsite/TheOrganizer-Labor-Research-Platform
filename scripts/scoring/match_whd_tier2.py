import os
from db_config import get_connection
"""
Match WHD Tier 2 (name + state only) for F7 and Mergent employers.
Runs AFTER match_whd_to_employers.py completed Tier 1 matching.

Tier 1 already completed: F7=2,990, Mergent=914
This script handles Tier 2 (name+state, unmatched only) more efficiently
by using a temp table with proper indexes instead of a CTE.
"""
import psycopg2
import time

conn = get_connection()
cur = conn.cursor()

print("=" * 70)
print("WHD TIER 2 MATCHING (name + state only)")
print("=" * 70)

# Step 1: Create indexed temp table for state-level aggregation
print("\nStep 1: Creating state-level aggregation table ...")
t0 = time.time()

cur.execute("DROP TABLE IF EXISTS tmp_whd_state_agg")
cur.execute("""
    CREATE TABLE tmp_whd_state_agg AS
    SELECT name_normalized, state,
        SUM(case_count)::integer as case_count,
        SUM(total_backwages)::numeric as total_backwages,
        SUM(total_employees_violated)::integer as total_employees_violated,
        SUM(total_penalties)::numeric as total_penalties,
        SUM(child_labor_violations)::integer as child_labor_violations,
        BOOL_OR(is_repeat_violator) as is_repeat_violator
    FROM mv_whd_employer_agg
    GROUP BY name_normalized, state
""")
conn.commit()

cur.execute("SELECT COUNT(*) FROM tmp_whd_state_agg")
print(f"  State-level aggregated rows: {cur.fetchone()[0]:,}")

# Create indexes for fast joins
cur.execute("CREATE INDEX idx_tmp_whd_sa_name_state ON tmp_whd_state_agg(name_normalized, state)")
conn.commit()
print(f"  Index created. Time: {time.time()-t0:.1f}s")

# Step 2: Tier 2 F7 matching
print("\nStep 2: Tier 2 F7 matching (name + state, unmatched only) ...")
t1 = time.time()

cur.execute("""
    UPDATE f7_employers_deduped f
    SET whd_violation_count = w.case_count,
        whd_backwages = w.total_backwages,
        whd_employees_violated = w.total_employees_violated,
        whd_penalties = w.total_penalties,
        whd_child_labor = w.child_labor_violations,
        whd_repeat_violator = w.is_repeat_violator
    FROM tmp_whd_state_agg w
    WHERE f.employer_name_aggressive = w.name_normalized
      AND f.state = w.state
      AND f.whd_violation_count IS NULL
""")
f7_tier2 = cur.rowcount
conn.commit()
print(f"  F7 Tier 2 matches: {f7_tier2:,} (time: {time.time()-t1:.1f}s)")

# Step 3: Tier 2 Mergent matching
print("\nStep 3: Tier 2 Mergent matching (name + state, unmatched only) ...")
t2 = time.time()

cur.execute("""
    UPDATE mergent_employers m
    SET whd_violation_count = w.case_count,
        whd_backwages = w.total_backwages,
        whd_employees_violated = w.total_employees_violated,
        whd_penalties = w.total_penalties,
        whd_child_labor = w.child_labor_violations,
        whd_repeat_violator = w.is_repeat_violator,
        whd_match_method = 'WHD_NATIONAL_STATE'
    FROM tmp_whd_state_agg w
    WHERE m.company_name_normalized = w.name_normalized
      AND m.state = w.state
      AND m.whd_violation_count IS NULL
""")
mergent_tier2 = cur.rowcount
conn.commit()
print(f"  Mergent Tier 2 matches: {mergent_tier2:,} (time: {time.time()-t2:.1f}s)")

# Cleanup
cur.execute("DROP TABLE IF EXISTS tmp_whd_state_agg")
conn.commit()

# Step 4: Final statistics
print("\n" + "=" * 70)
print("FINAL MATCH STATISTICS")
print("=" * 70)

# F7 totals
cur.execute("SELECT COUNT(*) FROM f7_employers_deduped WHERE whd_violation_count IS NOT NULL")
f7_total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM f7_employers_deduped")
f7_all = cur.fetchone()[0]
print(f"\nF7 Employers:")
print(f"  Tier 1 (name+city+state): 2,990")
print(f"  Tier 2 (name+state):      {f7_tier2:,}")
print(f"  Total matched:            {f7_total:,} / {f7_all:,} ({100*f7_total/f7_all:.1f}%)")

cur.execute("""
    SELECT SUM(whd_violation_count), SUM(whd_backwages), SUM(whd_employees_violated),
           SUM(whd_penalties), SUM(whd_child_labor),
           COUNT(*) FILTER (WHERE whd_repeat_violator)
    FROM f7_employers_deduped
    WHERE whd_violation_count IS NOT NULL
""")
r = cur.fetchone()
print(f"  Total WHD violations:     {r[0]:,}" if r[0] else "  Total WHD violations:     0")
print(f"  Total backwages:          ${r[1]:,.2f}" if r[1] else "  Total backwages:          $0.00")
print(f"  Total employees violated: {r[2]:,}" if r[2] else "  Total employees violated: 0")
print(f"  Total penalties:          ${r[3]:,.2f}" if r[3] else "  Total penalties:          $0.00")
print(f"  Repeat violators:         {r[5]:,}" if r[5] else "  Repeat violators:         0")

# Mergent totals
cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE whd_violation_count IS NOT NULL")
m_total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM mergent_employers")
m_all = cur.fetchone()[0]
print(f"\nMergent Employers:")
print(f"  Tier 1 (name+city+state): 914")
print(f"  Tier 2 (name+state):      {mergent_tier2:,}")
print(f"  Total matched:            {m_total:,} / {m_all:,} ({100*m_total/m_all:.1f}%)")

cur.execute("""
    SELECT SUM(whd_violation_count), SUM(whd_backwages), SUM(whd_employees_violated),
           SUM(whd_penalties),
           COUNT(*) FILTER (WHERE whd_repeat_violator)
    FROM mergent_employers
    WHERE whd_violation_count IS NOT NULL
""")
r = cur.fetchone()
print(f"  Total WHD violations:     {r[0]:,}" if r[0] else "  Total WHD violations:     0")
print(f"  Total backwages:          ${r[1]:,.2f}" if r[1] else "  Total backwages:          $0.00")
print(f"  Total employees violated: {r[2]:,}" if r[2] else "  Total employees violated: 0")
print(f"  Total penalties:          ${r[3]:,.2f}" if r[3] else "  Total penalties:          $0.00")
print(f"  Repeat violators:         {r[4]:,}" if r[4] else "  Repeat violators:         0")

cur.execute("""
    SELECT whd_match_method, COUNT(*)
    FROM mergent_employers
    WHERE whd_violation_count IS NOT NULL
    GROUP BY whd_match_method
    ORDER BY COUNT(*) DESC
""")
print(f"\n  Match method breakdown:")
for r in cur.fetchall():
    print(f"    {r[0]}: {r[1]:,}")

# Top 10 F7 by backwages
print("\nTop 10 F7 Employers by Backwages:")
cur.execute("""
    SELECT employer_name_aggressive, state, city,
           whd_violation_count, whd_backwages, whd_employees_violated
    FROM f7_employers_deduped
    WHERE whd_backwages IS NOT NULL AND whd_backwages > 0
    ORDER BY whd_backwages DESC
    LIMIT 10
""")
for i, r in enumerate(cur.fetchall(), 1):
    name = (r[0] or '')[:40]
    st = r[1] or ''
    city = (r[2] or '')[:15]
    print(f"  {i:2d}. {name:<40s} {city:<15s} {st}  viol={r[3]:,}  bw=${r[4]:,.0f}  emp={r[5]:,}")

# Top 10 Mergent by backwages
print("\nTop 10 Mergent Employers by Backwages:")
cur.execute("""
    SELECT company_name, state, city,
           whd_violation_count, whd_backwages, whd_employees_violated
    FROM mergent_employers
    WHERE whd_backwages IS NOT NULL AND whd_backwages > 0
    ORDER BY whd_backwages DESC
    LIMIT 10
""")
for i, r in enumerate(cur.fetchall(), 1):
    name = (r[0] or '')[:40]
    st = r[1] or ''
    city = (r[2] or '')[:15]
    print(f"  {i:2d}. {name:<40s} {city:<15s} {st}  viol={r[3]:,}  bw=${r[4]:,.0f}  emp={r[5]:,}")

cur.close()
conn.close()

print(f"\nTotal time: {time.time()-t0:.1f}s")
print("\n" + "=" * 70)
print("WHD TIER 2 MATCHING COMPLETE")
print("=" * 70)
