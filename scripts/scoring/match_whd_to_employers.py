import os
from db_config import get_connection
"""
Match WHD (Wage and Hour Division) national cases to F7 and Mergent employers.

Prerequisites: whd_cases table must exist (loaded by load_whd_national.py)

Matching tiers:
  Tier 1: name_normalized + state + UPPER(city)  (HIGH confidence)
  Tier 2: name_normalized + state only            (MEDIUM confidence, unmatched only)
"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

print("=" * 70)
print("MATCHING WHD NATIONAL CASES TO F7 AND MERGENT EMPLOYERS")
print("=" * 70)

# =====================================================================
# Step 1: Create materialized view mv_whd_employer_agg
# =====================================================================
print("\n=== Step 1: Creating materialized view mv_whd_employer_agg ===")

cur.execute("DROP MATERIALIZED VIEW IF EXISTS mv_whd_employer_agg")
conn.commit()

cur.execute("""
    CREATE MATERIALIZED VIEW mv_whd_employer_agg AS
    SELECT
        name_normalized,
        UPPER(city) as city,
        state,
        COUNT(*) as case_count,
        SUM(COALESCE(total_violations, 0)) as total_violations,
        SUM(COALESCE(backwages_amount, 0)) as total_backwages,
        SUM(COALESCE(employees_violated, 0)) as total_employees_violated,
        SUM(COALESCE(civil_penalties, 0)) as total_penalties,
        SUM(COALESCE(flsa_child_labor_violations, 0)) as child_labor_violations,
        SUM(COALESCE(flsa_child_labor_minors, 0)) as child_labor_minors,
        BOOL_OR(COALESCE(flsa_repeat_violator, FALSE)) as is_repeat_violator,
        MAX(findings_end_date) as latest_finding,
        MIN(findings_start_date) as earliest_finding
    FROM whd_cases
    WHERE name_normalized IS NOT NULL AND name_normalized != ''
    GROUP BY name_normalized, UPPER(city), state
""")
conn.commit()
print("  Materialized view created")

cur.execute("CREATE INDEX idx_mv_whd_name_state ON mv_whd_employer_agg(name_normalized, state)")
cur.execute("CREATE INDEX idx_mv_whd_name_city_state ON mv_whd_employer_agg(name_normalized, city, state)")
conn.commit()
print("  Indexes created")

cur.execute("SELECT COUNT(*) FROM mv_whd_employer_agg")
mv_count = cur.fetchone()[0]
print(f"  Aggregated WHD records: {mv_count:,}")

# =====================================================================
# Step 2: Add WHD columns to f7_employers_deduped and mergent_employers
# =====================================================================
print("\n=== Step 2: Adding WHD columns to employer tables ===")

# F7 columns (all new)
f7_columns = [
    ("whd_violation_count", "INTEGER"),
    ("whd_backwages", "NUMERIC"),
    ("whd_employees_violated", "INTEGER"),
    ("whd_penalties", "NUMERIC"),
    ("whd_child_labor", "INTEGER"),
    ("whd_repeat_violator", "BOOLEAN"),
]

for col_name, col_type in f7_columns:
    cur.execute(f"ALTER TABLE f7_employers_deduped ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
conn.commit()
print("  F7 columns added/verified")

# Mergent columns (whd_violation_count, whd_backwages, whd_employees_violated, whd_match_method exist)
mergent_new_columns = [
    ("whd_penalties", "NUMERIC"),
    ("whd_child_labor", "INTEGER"),
    ("whd_repeat_violator", "BOOLEAN"),
]

for col_name, col_type in mergent_new_columns:
    cur.execute(f"ALTER TABLE mergent_employers ADD COLUMN IF NOT EXISTS {col_name} {col_type}")
conn.commit()
print("  Mergent columns added/verified")

# =====================================================================
# Step 3: Reset existing WHD data on both tables
# =====================================================================
print("\n=== Step 3: Resetting existing WHD data ===")

cur.execute("""
    UPDATE mergent_employers SET
        whd_violation_count = NULL,
        whd_backwages = NULL,
        whd_employees_violated = NULL,
        whd_match_method = NULL,
        whd_penalties = NULL,
        whd_child_labor = NULL,
        whd_repeat_violator = NULL
""")
mergent_reset = cur.rowcount
conn.commit()
print(f"  Mergent reset: {mergent_reset:,} rows")

cur.execute("""
    UPDATE f7_employers_deduped SET
        whd_violation_count = NULL,
        whd_backwages = NULL,
        whd_employees_violated = NULL,
        whd_penalties = NULL,
        whd_child_labor = NULL,
        whd_repeat_violator = NULL
""")
f7_reset = cur.rowcount
conn.commit()
print(f"  F7 reset: {f7_reset:,} rows")

# =====================================================================
# Step 4: Match to F7 employers
# =====================================================================
print("\n=== Step 4: Matching WHD to F7 employers ===")

# Tier 1: name + state + city (HIGH confidence)
print("  Tier 1: name + state + city ...")
cur.execute("""
    UPDATE f7_employers_deduped f
    SET whd_violation_count = w.case_count,
        whd_backwages = w.total_backwages,
        whd_employees_violated = w.total_employees_violated,
        whd_penalties = w.total_penalties,
        whd_child_labor = w.child_labor_violations,
        whd_repeat_violator = w.is_repeat_violator
    FROM mv_whd_employer_agg w
    WHERE f.employer_name_aggressive = w.name_normalized
      AND f.state = w.state
      AND UPPER(f.city) = w.city
""")
f7_tier1 = cur.rowcount
conn.commit()
print(f"  Tier 1 matches: {f7_tier1:,}")

# Tier 2: name + state only (MEDIUM confidence, unmatched only)
print("  Tier 2: name + state only (unmatched) ...")
cur.execute("""
    WITH whd_state_agg AS (
        SELECT name_normalized, state,
            SUM(case_count) as case_count,
            SUM(total_backwages) as total_backwages,
            SUM(total_employees_violated) as total_employees_violated,
            SUM(total_penalties) as total_penalties,
            SUM(child_labor_violations) as child_labor_violations,
            SUM(child_labor_minors) as child_labor_minors,
            BOOL_OR(is_repeat_violator) as is_repeat_violator
        FROM mv_whd_employer_agg
        GROUP BY name_normalized, state
    )
    UPDATE f7_employers_deduped f
    SET whd_violation_count = w.case_count,
        whd_backwages = w.total_backwages,
        whd_employees_violated = w.total_employees_violated,
        whd_penalties = w.total_penalties,
        whd_child_labor = w.child_labor_violations,
        whd_repeat_violator = w.is_repeat_violator
    FROM whd_state_agg w
    WHERE f.employer_name_aggressive = w.name_normalized
      AND f.state = w.state
      AND f.whd_violation_count IS NULL
""")
f7_tier2 = cur.rowcount
conn.commit()
print(f"  Tier 2 matches: {f7_tier2:,}")

f7_total = f7_tier1 + f7_tier2
print(f"  F7 total matched: {f7_total:,} / {f7_reset:,} ({100*f7_total/f7_reset:.1f}%)")

# =====================================================================
# Step 5: Match to Mergent employers
# =====================================================================
print("\n=== Step 5: Matching WHD to Mergent employers ===")

# Tier 1: name + state + city (HIGH confidence)
print("  Tier 1: name + state + city ...")
cur.execute("""
    UPDATE mergent_employers m
    SET whd_violation_count = w.case_count,
        whd_backwages = w.total_backwages,
        whd_employees_violated = w.total_employees_violated,
        whd_penalties = w.total_penalties,
        whd_child_labor = w.child_labor_violations,
        whd_repeat_violator = w.is_repeat_violator,
        whd_match_method = 'WHD_NATIONAL_CITY'
    FROM mv_whd_employer_agg w
    WHERE m.company_name_normalized = w.name_normalized
      AND m.state = w.state
      AND UPPER(m.city) = w.city
""")
mergent_tier1 = cur.rowcount
conn.commit()
print(f"  Tier 1 matches: {mergent_tier1:,}")

# Tier 2: name + state only (MEDIUM confidence, unmatched only)
print("  Tier 2: name + state only (unmatched) ...")
cur.execute("""
    WITH whd_state_agg AS (
        SELECT name_normalized, state,
            SUM(case_count) as case_count,
            SUM(total_backwages) as total_backwages,
            SUM(total_employees_violated) as total_employees_violated,
            SUM(total_penalties) as total_penalties,
            SUM(child_labor_violations) as child_labor_violations,
            SUM(child_labor_minors) as child_labor_minors,
            BOOL_OR(is_repeat_violator) as is_repeat_violator
        FROM mv_whd_employer_agg
        GROUP BY name_normalized, state
    )
    UPDATE mergent_employers m
    SET whd_violation_count = w.case_count,
        whd_backwages = w.total_backwages,
        whd_employees_violated = w.total_employees_violated,
        whd_penalties = w.total_penalties,
        whd_child_labor = w.child_labor_violations,
        whd_repeat_violator = w.is_repeat_violator,
        whd_match_method = 'WHD_NATIONAL_STATE'
    FROM whd_state_agg w
    WHERE m.company_name_normalized = w.name_normalized
      AND m.state = w.state
      AND m.whd_violation_count IS NULL
""")
mergent_tier2 = cur.rowcount
conn.commit()
print(f"  Tier 2 matches: {mergent_tier2:,}")

mergent_total = mergent_tier1 + mergent_tier2
print(f"  Mergent total matched: {mergent_total:,} / {mergent_reset:,} ({100*mergent_total/mergent_reset:.1f}%)")

# =====================================================================
# Step 6: Print match statistics
# =====================================================================
print("\n" + "=" * 70)
print("MATCH STATISTICS")
print("=" * 70)

print("\n--- F7 Employers ---")
print(f"  Tier 1 (name+city+state): {f7_tier1:,}")
print(f"  Tier 2 (name+state):      {f7_tier2:,}")
print(f"  Total matched:            {f7_total:,} / {f7_reset:,} ({100*f7_total/f7_reset:.1f}%)")

cur.execute("""
    SELECT SUM(whd_violation_count), SUM(whd_backwages), SUM(whd_employees_violated),
           SUM(whd_penalties), SUM(whd_child_labor),
           COUNT(*) FILTER (WHERE whd_repeat_violator)
    FROM f7_employers_deduped
    WHERE whd_violation_count IS NOT NULL
""")
r = cur.fetchone()
print(f"  Total violations:         {r[0]:,}" if r[0] else "  Total violations:         0")
print(f"  Total backwages:          ${r[1]:,.2f}" if r[1] else "  Total backwages:          $0.00")
print(f"  Total employees violated: {r[2]:,}" if r[2] else "  Total employees violated: 0")
print(f"  Total penalties:          ${r[3]:,.2f}" if r[3] else "  Total penalties:          $0.00")
print(f"  Child labor violations:   {r[4]:,}" if r[4] else "  Child labor violations:   0")
print(f"  Repeat violators:         {r[5]:,}" if r[5] else "  Repeat violators:         0")

print("\n--- Mergent Employers ---")
print(f"  Tier 1 (name+city+state): {mergent_tier1:,}")
print(f"  Tier 2 (name+state):      {mergent_tier2:,}")
print(f"  Total matched:            {mergent_total:,} / {mergent_reset:,} ({100*mergent_total/mergent_reset:.1f}%)")

cur.execute("""
    SELECT SUM(whd_violation_count), SUM(whd_backwages), SUM(whd_employees_violated),
           SUM(whd_penalties), SUM(whd_child_labor),
           COUNT(*) FILTER (WHERE whd_repeat_violator)
    FROM mergent_employers
    WHERE whd_violation_count IS NOT NULL
""")
r = cur.fetchone()
print(f"  Total violations:         {r[0]:,}" if r[0] else "  Total violations:         0")
print(f"  Total backwages:          ${r[1]:,.2f}" if r[1] else "  Total backwages:          $0.00")
print(f"  Total employees violated: {r[2]:,}" if r[2] else "  Total employees violated: 0")
print(f"  Total penalties:          ${r[3]:,.2f}" if r[3] else "  Total penalties:          $0.00")
print(f"  Child labor violations:   {r[4]:,}" if r[4] else "  Child labor violations:   0")
print(f"  Repeat violators:         {r[5]:,}" if r[5] else "  Repeat violators:         0")

cur.execute("""
    SELECT COUNT(*) FILTER (WHERE whd_match_method = 'WHD_NATIONAL_CITY'),
           COUNT(*) FILTER (WHERE whd_match_method = 'WHD_NATIONAL_STATE')
    FROM mergent_employers
    WHERE whd_violation_count IS NOT NULL
""")
r = cur.fetchone()
print(f"  By method - WHD_NATIONAL_CITY:  {r[0]:,}")
print(f"  By method - WHD_NATIONAL_STATE: {r[1]:,}")

# Top 10 F7 employers by backwages
print("\n--- Top 10 F7 Employers by Backwages ---")
cur.execute("""
    SELECT employer_name_aggressive, state, city,
           whd_violation_count, whd_backwages, whd_employees_violated
    FROM f7_employers_deduped
    WHERE whd_backwages IS NOT NULL AND whd_backwages > 0
    ORDER BY whd_backwages DESC
    LIMIT 10
""")
rows = cur.fetchall()
for i, r in enumerate(rows, 1):
    name = r[0][:40] if r[0] else ''
    state = r[1] or ''
    city = r[2] or ''
    viol = r[3] or 0
    bw = r[4] or 0
    emp = r[5] or 0
    print(f"  {i:2d}. {name:<40s} {city:<15s} {state}  violations={viol:,}  backwages=${bw:,.0f}  employees={emp:,}")

# Top 10 Mergent employers by backwages
print("\n--- Top 10 Mergent Employers by Backwages ---")
cur.execute("""
    SELECT company_name, state, city,
           whd_violation_count, whd_backwages, whd_employees_violated
    FROM mergent_employers
    WHERE whd_backwages IS NOT NULL AND whd_backwages > 0
    ORDER BY whd_backwages DESC
    LIMIT 10
""")
rows = cur.fetchall()
for i, r in enumerate(rows, 1):
    name = r[0][:40] if r[0] else ''
    state = r[1] or ''
    city = r[2] or ''
    viol = r[3] or 0
    bw = r[4] or 0
    emp = r[5] or 0
    print(f"  {i:2d}. {name:<40s} {city:<15s} {state}  violations={viol:,}  backwages=${bw:,.0f}  employees={emp:,}")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("WHD MATCHING COMPLETE")
print("=" * 70)
