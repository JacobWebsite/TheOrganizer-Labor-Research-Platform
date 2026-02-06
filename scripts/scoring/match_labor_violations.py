"""
Match Mergent employers to NYC Comptroller labor violation data
and calculate score_labor_violations
"""
import psycopg2
import re

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

print("=" * 70)
print("MATCHING NYC COMPTROLLER LABOR VIOLATIONS")
print("=" * 70)

# Step 1: Add columns if they don't exist
print("\n=== Step 1: Adding violation columns ===")
new_columns = [
    ("nyc_wage_theft_cases", "INTEGER DEFAULT 0"),
    ("nyc_wage_theft_amount", "NUMERIC(15,2) DEFAULT 0"),
    ("nyc_ulp_cases", "INTEGER DEFAULT 0"),
    ("nyc_local_law_cases", "INTEGER DEFAULT 0"),
    ("nyc_local_law_amount", "NUMERIC(15,2) DEFAULT 0"),
    ("nyc_debarred", "BOOLEAN DEFAULT FALSE"),
    ("score_labor_violations", "INTEGER DEFAULT 0"),
]

for col_name, col_type in new_columns:
    try:
        cur.execute(f"ALTER TABLE mergent_employers ADD COLUMN {col_name} {col_type}")
        print(f"  Added column: {col_name}")
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
        print(f"  Column exists: {col_name}")
conn.commit()

# Helper function to normalize names for matching
def normalize_for_match(name):
    if not name:
        return ''
    # Uppercase, remove punctuation, common suffixes
    name = name.upper()
    name = re.sub(r'[^\w\s]', ' ', name)
    name = re.sub(r'\b(INC|LLC|CORP|CO|LTD|LP|LLP|THE|OF|AND)\b', '', name)
    name = ' '.join(name.split())
    return name.strip()[:250]  # Truncate to fit VARCHAR(255)

# Step 2: Create normalized name index for NYC tables
print("\n=== Step 2: Adding normalized names to NYC tables ===")

# Add normalized columns to NYC tables
for table in ['nyc_wage_theft_nys', 'nyc_wage_theft_usdol', 'nyc_ulp_closed', 'nyc_ulp_open',
              'nyc_local_labor_laws', 'nyc_debarment_list']:
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN employer_name_normalized VARCHAR(255)")
        print(f"  Added normalized column to {table}")
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
        print(f"  Normalized column exists in {table}")
conn.commit()

# Populate normalized names
print("\n=== Step 3: Populating normalized names ===")

# NYC Wage Theft NYS
cur.execute("SELECT id, employer_name FROM nyc_wage_theft_nys WHERE employer_name_normalized IS NULL")
rows = cur.fetchall()
for row_id, name in rows:
    norm = normalize_for_match(name)
    cur.execute("UPDATE nyc_wage_theft_nys SET employer_name_normalized = %s WHERE id = %s", [norm, row_id])
print(f"  nyc_wage_theft_nys: {len(rows)} normalized")
conn.commit()

# NYC Wage Theft USDOL
cur.execute("SELECT id, trade_name FROM nyc_wage_theft_usdol WHERE employer_name_normalized IS NULL")
rows = cur.fetchall()
for row_id, name in rows:
    norm = normalize_for_match(name)
    cur.execute("UPDATE nyc_wage_theft_usdol SET employer_name_normalized = %s WHERE id = %s", [norm, row_id])
print(f"  nyc_wage_theft_usdol: {len(rows)} normalized")
conn.commit()

# NYC ULP Closed
cur.execute("SELECT id, employer FROM nyc_ulp_closed WHERE employer_name_normalized IS NULL")
rows = cur.fetchall()
for row_id, name in rows:
    norm = normalize_for_match(name)
    cur.execute("UPDATE nyc_ulp_closed SET employer_name_normalized = %s WHERE id = %s", [norm, row_id])
print(f"  nyc_ulp_closed: {len(rows)} normalized")
conn.commit()

# NYC ULP Open
cur.execute("SELECT id, employer FROM nyc_ulp_open WHERE employer_name_normalized IS NULL")
rows = cur.fetchall()
for row_id, name in rows:
    norm = normalize_for_match(name)
    cur.execute("UPDATE nyc_ulp_open SET employer_name_normalized = %s WHERE id = %s", [norm, row_id])
print(f"  nyc_ulp_open: {len(rows)} normalized")
conn.commit()

# NYC Local Labor Laws
cur.execute("SELECT id, employer_name FROM nyc_local_labor_laws WHERE employer_name_normalized IS NULL")
rows = cur.fetchall()
for row_id, name in rows:
    norm = normalize_for_match(name)
    cur.execute("UPDATE nyc_local_labor_laws SET employer_name_normalized = %s WHERE id = %s", [norm, row_id])
print(f"  nyc_local_labor_laws: {len(rows)} normalized")
conn.commit()

# NYC Debarment List
cur.execute("SELECT id, employer_name FROM nyc_debarment_list WHERE employer_name_normalized IS NULL")
rows = cur.fetchall()
for row_id, name in rows:
    norm = normalize_for_match(name)
    cur.execute("UPDATE nyc_debarment_list SET employer_name_normalized = %s WHERE id = %s", [norm, row_id])
print(f"  nyc_debarment_list: {len(rows)} normalized")
conn.commit()

# Step 4: Match and aggregate violations
print("\n=== Step 4: Matching violations to Mergent employers ===")

# Reset violation columns
cur.execute("""
    UPDATE mergent_employers SET
        nyc_wage_theft_cases = 0,
        nyc_wage_theft_amount = 0,
        nyc_ulp_cases = 0,
        nyc_local_law_cases = 0,
        nyc_local_law_amount = 0,
        nyc_debarred = FALSE,
        score_labor_violations = 0
""")
print(f"  Reset {cur.rowcount:,} rows")
conn.commit()

# Match NYC Wage Theft (NYS DOL) - by normalized name
cur.execute("""
    WITH wage_theft AS (
        SELECT
            employer_name_normalized as norm_name,
            COUNT(*) as case_count,
            SUM(COALESCE(wages_owed, 0)) as total_wages
        FROM nyc_wage_theft_nys
        WHERE employer_name_normalized IS NOT NULL AND employer_name_normalized != ''
        GROUP BY employer_name_normalized
    )
    UPDATE mergent_employers m
    SET
        nyc_wage_theft_cases = COALESCE(m.nyc_wage_theft_cases, 0) + w.case_count,
        nyc_wage_theft_amount = COALESCE(m.nyc_wage_theft_amount, 0) + w.total_wages
    FROM wage_theft w
    WHERE UPPER(REGEXP_REPLACE(m.company_name_normalized, '[^A-Z0-9 ]', '', 'g')) = w.norm_name
       OR UPPER(REGEXP_REPLACE(m.company_name_normalized, '[^A-Z0-9 ]', '', 'g')) LIKE w.norm_name || '%'
""")
print(f"  NYS DOL wage theft: {cur.rowcount} matches")
conn.commit()

# Match NYC Wage Theft (US DOL) - by normalized name
cur.execute("""
    WITH wage_theft AS (
        SELECT
            employer_name_normalized as norm_name,
            COUNT(*) as case_count,
            SUM(COALESCE(backwages_amount, 0)) as total_wages
        FROM nyc_wage_theft_usdol
        WHERE employer_name_normalized IS NOT NULL AND employer_name_normalized != ''
        GROUP BY employer_name_normalized
    )
    UPDATE mergent_employers m
    SET
        nyc_wage_theft_cases = COALESCE(m.nyc_wage_theft_cases, 0) + w.case_count,
        nyc_wage_theft_amount = COALESCE(m.nyc_wage_theft_amount, 0) + w.total_wages
    FROM wage_theft w
    WHERE UPPER(REGEXP_REPLACE(m.company_name_normalized, '[^A-Z0-9 ]', '', 'g')) = w.norm_name
""")
print(f"  US DOL wage theft: {cur.rowcount} matches")
conn.commit()

# Match NYC ULP cases (closed + open)
cur.execute("""
    WITH ulp AS (
        SELECT employer_name_normalized as norm_name, COUNT(*) as case_count
        FROM nyc_ulp_closed
        WHERE employer_name_normalized IS NOT NULL AND employer_name_normalized != ''
        GROUP BY employer_name_normalized
        UNION ALL
        SELECT employer_name_normalized as norm_name, COUNT(*) as case_count
        FROM nyc_ulp_open
        WHERE employer_name_normalized IS NOT NULL AND employer_name_normalized != ''
        GROUP BY employer_name_normalized
    ),
    ulp_agg AS (
        SELECT norm_name, SUM(case_count) as total_cases FROM ulp GROUP BY norm_name
    )
    UPDATE mergent_employers m
    SET nyc_ulp_cases = u.total_cases
    FROM ulp_agg u
    WHERE UPPER(REGEXP_REPLACE(m.company_name_normalized, '[^A-Z0-9 ]', '', 'g')) = u.norm_name
""")
print(f"  ULP cases: {cur.rowcount} matches")
conn.commit()

# Match NYC Local Labor Laws (PSSL, Fair Workweek, etc.)
cur.execute("""
    WITH local_laws AS (
        SELECT
            employer_name_normalized as norm_name,
            COUNT(*) as case_count,
            SUM(COALESCE(total_recovered, 0)) as total_amount
        FROM nyc_local_labor_laws
        WHERE employer_name_normalized IS NOT NULL AND employer_name_normalized != ''
        GROUP BY employer_name_normalized
    )
    UPDATE mergent_employers m
    SET
        nyc_local_law_cases = l.case_count,
        nyc_local_law_amount = l.total_amount
    FROM local_laws l
    WHERE UPPER(REGEXP_REPLACE(m.company_name_normalized, '[^A-Z0-9 ]', '', 'g')) = l.norm_name
""")
print(f"  Local labor laws: {cur.rowcount} matches")
conn.commit()

# Match NYC Debarment List
cur.execute("""
    UPDATE mergent_employers m
    SET nyc_debarred = TRUE
    FROM nyc_debarment_list d
    WHERE UPPER(REGEXP_REPLACE(m.company_name_normalized, '[^A-Z0-9 ]', '', 'g')) = d.employer_name_normalized
      AND d.employer_name_normalized IS NOT NULL AND d.employer_name_normalized != ''
""")
print(f"  Debarred employers: {cur.rowcount} matches")
conn.commit()

# Step 5: Calculate score_labor_violations (0-10 points)
print("\n=== Step 5: Calculating labor violation scores ===")
cur.execute("""
    UPDATE mergent_employers
    SET score_labor_violations =
        -- Wage theft (0-4 points)
        CASE
            WHEN nyc_wage_theft_amount >= 100000 THEN 4
            WHEN nyc_wage_theft_amount >= 50000 THEN 3
            WHEN nyc_wage_theft_amount >= 10000 THEN 2
            WHEN nyc_wage_theft_cases > 0 THEN 1
            ELSE 0
        END
        +
        -- ULP cases (0-3 points)
        CASE
            WHEN nyc_ulp_cases >= 3 THEN 3
            WHEN nyc_ulp_cases >= 2 THEN 2
            WHEN nyc_ulp_cases >= 1 THEN 1
            ELSE 0
        END
        +
        -- Local labor law violations (0-2 points)
        CASE
            WHEN nyc_local_law_cases >= 2 THEN 2
            WHEN nyc_local_law_cases >= 1 THEN 1
            ELSE 0
        END
        +
        -- Debarment (0-1 point)
        CASE WHEN nyc_debarred THEN 1 ELSE 0 END
""")
print(f"  Calculated scores for {cur.rowcount:,} rows")
conn.commit()

# Step 6: Update organizing_score to include labor violations
print("\n=== Step 6: Updating organizing scores ===")
cur.execute("""
    UPDATE mergent_employers
    SET organizing_score = COALESCE(score_geographic, 0)
                         + COALESCE(score_size, 0)
                         + COALESCE(score_industry_density, 0)
                         + COALESCE(score_nlrb_momentum, 0)
                         + COALESCE(score_osha_violations, 0)
                         + COALESCE(score_govt_contracts, 0)
                         + COALESCE(sibling_union_bonus, 0)
                         + COALESCE(score_labor_violations, 0)
    WHERE has_union IS NOT TRUE
""")
print(f"  Updated {cur.rowcount:,} organizing scores")
conn.commit()

# Step 7: Update priority tiers
print("\n=== Step 7: Updating priority tiers ===")
cur.execute("""
    UPDATE mergent_employers
    SET score_priority = CASE
        WHEN organizing_score >= 30 THEN 'TOP'
        WHEN organizing_score >= 25 THEN 'HIGH'
        WHEN organizing_score >= 15 THEN 'MEDIUM'
        ELSE 'LOW'
    END
    WHERE has_union IS NOT TRUE
""")
print(f"  Updated {cur.rowcount:,} tiers")
conn.commit()

# Summary
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE nyc_wage_theft_cases > 0) as with_wage_theft,
        COUNT(*) FILTER (WHERE nyc_ulp_cases > 0) as with_ulp,
        COUNT(*) FILTER (WHERE nyc_local_law_cases > 0) as with_local_law,
        COUNT(*) FILTER (WHERE nyc_debarred) as debarred,
        COUNT(*) FILTER (WHERE score_labor_violations > 0) as with_any_violation,
        SUM(nyc_wage_theft_amount) as total_wage_theft
    FROM mergent_employers
""")
r = cur.fetchone()
print(f"Employers with wage theft cases: {r[0]:,}")
print(f"Employers with ULP cases: {r[1]:,}")
print(f"Employers with local law violations: {r[2]:,}")
print(f"Debarred employers: {r[3]:,}")
print(f"Employers with ANY violation: {r[4]:,}")
print(f"Total wage theft amount: ${r[5]:,.2f}" if r[5] else "Total wage theft amount: $0")

print("\n=== Score Distribution ===")
cur.execute("""
    SELECT score_labor_violations, COUNT(*)
    FROM mergent_employers
    WHERE score_labor_violations > 0
    GROUP BY score_labor_violations
    ORDER BY score_labor_violations DESC
""")
for r in cur.fetchall():
    print(f"  {r[0]} points: {r[1]:,} employers")

print("\n=== Updated Tier Distribution ===")
cur.execute("""
    SELECT
        score_priority,
        COUNT(*) as count,
        ROUND(AVG(organizing_score), 1) as avg_score
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
    GROUP BY score_priority
    ORDER BY CASE score_priority WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 WHEN 'LOW' THEN 4 END
""")
for r in cur.fetchall():
    print(f"  {r[0]}: {r[1]:,} targets (avg score: {r[2]})")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("LABOR VIOLATION MATCHING COMPLETE")
print("=" * 70)
