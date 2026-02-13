"""
Audit: Data Coverage for Gower Distance Similarity Engine
==========================================================
Checks mergent_employers + crosswalk coverage across all dimensions
that would feed into employer similarity scoring.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# ============================================================
# SECTION 0: Totals
# ============================================================
print("=" * 80)
print("GOWER DISTANCE SIMILARITY ENGINE - DATA COVERAGE AUDIT")
print("=" * 80)

cur.execute("SELECT COUNT(*) FROM mergent_employers")
total = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE has_union = TRUE")
union_count = cur.fetchone()[0]
cur.execute("SELECT COUNT(*) FROM mergent_employers WHERE has_union IS NOT TRUE")
nonunion_count = cur.fetchone()[0]

print(f"\nTotal employers:        {total:>8,}")
print(f"  Unionized (ref set):  {union_count:>8,}  ({100*union_count/total:.1f}%)")
print(f"  Non-union (targets):  {nonunion_count:>8,}  ({100*nonunion_count/total:.1f}%)")

# Helper function
def audit_field(label, where_clause, extra_join=""):
    """Run coverage query for a field, split by union status."""
    sql = f"""
        SELECT
            COUNT(*) AS total_with,
            COUNT(*) FILTER (WHERE m.has_union = TRUE) AS union_with,
            COUNT(*) FILTER (WHERE m.has_union IS NOT TRUE) AS nonunion_with
        FROM mergent_employers m
        {extra_join}
        WHERE {where_clause}
    """
    cur.execute(sql)
    row = cur.fetchone()
    total_w, union_w, nonunion_w = row
    pct_total = 100 * total_w / total if total else 0
    pct_union = 100 * union_w / union_count if union_count else 0
    pct_nonunion = 100 * nonunion_w / nonunion_count if nonunion_count else 0
    print(f"  {label:42s}  {total_w:>7,} ({pct_total:5.1f}%)   "
          f"U: {union_w:>6,} ({pct_union:5.1f}%)   "
          f"NU: {nonunion_w:>6,} ({pct_nonunion:5.1f}%)")
    return total_w, union_w, nonunion_w

# ============================================================
# SECTION 1: NAICS
# ============================================================
print("\n" + "-" * 80)
print("1. NAICS CODE COVERAGE")
print("-" * 80)
audit_field("Has naics_primary", "m.naics_primary IS NOT NULL")
audit_field("  6-digit NAICS", "m.naics_primary IS NOT NULL AND LENGTH(m.naics_primary) = 6")
audit_field("  4-digit NAICS", "m.naics_primary IS NOT NULL AND LENGTH(m.naics_primary) = 4")
audit_field("  2-digit NAICS", "m.naics_primary IS NOT NULL AND LENGTH(m.naics_primary) = 2")
audit_field("Has naics_secondary", "m.naics_secondary IS NOT NULL")
audit_field("Has sic_primary", "m.sic_primary IS NOT NULL")
audit_field("Has sector_category", "m.sector_category IS NOT NULL")

# NAICS distribution
cur.execute("""
    SELECT LENGTH(naics_primary) AS len, COUNT(*)
    FROM mergent_employers
    WHERE naics_primary IS NOT NULL
    GROUP BY LENGTH(naics_primary)
    ORDER BY len
""")
print("\n  NAICS length distribution:")
for row in cur:
    print(f"    {row[0]}-digit: {row[1]:>7,}")

# Top sectors
cur.execute("""
    SELECT LEFT(naics_primary, 2) AS sector, COUNT(*) AS cnt,
           COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
           COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM mergent_employers
    WHERE naics_primary IS NOT NULL
    GROUP BY LEFT(naics_primary, 2)
    ORDER BY cnt DESC
    LIMIT 15
""")
print("\n  Top 15 NAICS 2-digit sectors:")
print(f"    {'Sector':8s} {'Total':>8s} {'Union':>8s} {'Non-Un':>8s} {'U%':>6s}")
for row in cur:
    upct = f"{100*row[2]/(row[2]+row[3]):.0f}%" if (row[2]+row[3]) > 0 else "n/a"
    print(f"    {row[0]:8s} {row[1]:>8,} {row[2]:>8,} {row[3]:>8,} {upct:>6s}")

# ============================================================
# SECTION 2: EMPLOYEE COUNT
# ============================================================
print("\n" + "-" * 80)
print("2. EMPLOYEE COUNT COVERAGE")
print("-" * 80)
audit_field("Has employees_site", "m.employees_site IS NOT NULL AND m.employees_site > 0")
audit_field("Has employees_all_sites", "m.employees_all_sites IS NOT NULL AND m.employees_all_sites > 0")
audit_field("Has ny990_employees", "m.ny990_employees IS NOT NULL AND m.ny990_employees > 0")
audit_field("Has ANY employee count",
            "(m.employees_site IS NOT NULL AND m.employees_site > 0) OR "
            "(m.employees_all_sites IS NOT NULL AND m.employees_all_sites > 0) OR "
            "(m.ny990_employees IS NOT NULL AND m.ny990_employees > 0)")

# Employee size distribution
cur.execute("""
    SELECT
        CASE
            WHEN COALESCE(employees_site, employees_all_sites, ny990_employees) < 10 THEN '1-9'
            WHEN COALESCE(employees_site, employees_all_sites, ny990_employees) < 50 THEN '10-49'
            WHEN COALESCE(employees_site, employees_all_sites, ny990_employees) < 100 THEN '50-99'
            WHEN COALESCE(employees_site, employees_all_sites, ny990_employees) < 500 THEN '100-499'
            WHEN COALESCE(employees_site, employees_all_sites, ny990_employees) < 1000 THEN '500-999'
            WHEN COALESCE(employees_site, employees_all_sites, ny990_employees) < 5000 THEN '1000-4999'
            ELSE '5000+'
        END AS size_bucket,
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM mergent_employers
    WHERE COALESCE(employees_site, employees_all_sites, ny990_employees) IS NOT NULL
      AND COALESCE(employees_site, employees_all_sites, ny990_employees) > 0
    GROUP BY 1
    ORDER BY MIN(COALESCE(employees_site, employees_all_sites, ny990_employees))
""")
print("\n  Employee size distribution:")
print(f"    {'Bucket':12s} {'Total':>8s} {'Union':>8s} {'Non-Un':>8s}")
for row in cur:
    print(f"    {row[0]:12s} {row[1]:>8,} {row[2]:>8,} {row[3]:>8,}")

# ============================================================
# SECTION 3: REVENUE / FINANCIALS
# ============================================================
print("\n" + "-" * 80)
print("3. REVENUE / FINANCIALS COVERAGE")
print("-" * 80)
audit_field("Has sales_amount", "m.sales_amount IS NOT NULL AND m.sales_amount > 0")
audit_field("Has ny990_revenue", "m.ny990_revenue IS NOT NULL AND m.ny990_revenue > 0")
audit_field("Has ANY financial data",
            "(m.sales_amount IS NOT NULL AND m.sales_amount > 0) OR "
            "(m.ny990_revenue IS NOT NULL AND m.ny990_revenue > 0)")

# Revenue distribution
cur.execute("""
    SELECT
        CASE
            WHEN val < 100000 THEN 'Under 100K'
            WHEN val < 1000000 THEN '100K-1M'
            WHEN val < 10000000 THEN '1M-10M'
            WHEN val < 100000000 THEN '10M-100M'
            WHEN val < 1000000000 THEN '100M-1B'
            ELSE '1B+'
        END AS bucket,
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM (
        SELECT COALESCE(sales_amount, ny990_revenue) AS val, has_union
        FROM mergent_employers
        WHERE COALESCE(sales_amount, ny990_revenue) IS NOT NULL
          AND COALESCE(sales_amount, ny990_revenue) > 0
    ) sub
    GROUP BY 1
    ORDER BY MIN(val)
""")
print("\n  Revenue distribution:")
print(f"    {'Bucket':14s} {'Total':>8s} {'Union':>8s} {'Non-Un':>8s}")
for row in cur:
    print(f"    {row[0]:14s} {row[1]:>8,} {row[2]:>8,} {row[3]:>8,}")

# ============================================================
# SECTION 4: GEOGRAPHIC
# ============================================================
print("\n" + "-" * 80)
print("4. GEOGRAPHIC COVERAGE")
print("-" * 80)
audit_field("Has state", "m.state IS NOT NULL")
audit_field("Has city", "m.city IS NOT NULL")
audit_field("Has county", "m.county IS NOT NULL")
audit_field("Has zip", "m.zip IS NOT NULL")
audit_field("Has lat/lon", "m.latitude IS NOT NULL AND m.longitude IS NOT NULL")
audit_field("Has state + city", "m.state IS NOT NULL AND m.city IS NOT NULL")

# State distribution (top 15)
cur.execute("""
    SELECT state, COUNT(*) AS total,
           COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
           COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM mergent_employers
    WHERE state IS NOT NULL
    GROUP BY state
    ORDER BY total DESC
    LIMIT 15
""")
print("\n  Top 15 states:")
print(f"    {'State':6s} {'Total':>8s} {'Union':>8s} {'Non-Un':>8s} {'U%':>6s}")
for row in cur:
    upct = f"{100*row[2]/(row[2]+row[3]):.0f}%" if (row[2]+row[3]) > 0 else "n/a"
    print(f"    {row[0]:6s} {row[1]:>8,} {row[2]:>8,} {row[3]:>8,} {upct:>6s}")

# ============================================================
# SECTION 5: OSHA VIOLATIONS
# ============================================================
print("\n" + "-" * 80)
print("5. OSHA VIOLATIONS COVERAGE")
print("-" * 80)
audit_field("Has matched_osha_id", "m.matched_osha_id IS NOT NULL")
audit_field("Has osha_violation_count > 0", "m.osha_violation_count IS NOT NULL AND m.osha_violation_count > 0")
audit_field("Has osha_total_penalties > 0", "m.osha_total_penalties IS NOT NULL AND m.osha_total_penalties > 0")
audit_field("Has osha_total_inspections > 0", "m.osha_total_inspections IS NOT NULL AND m.osha_total_inspections > 0")

# ============================================================
# SECTION 6: GOVERNMENT CONTRACTS
# ============================================================
print("\n" + "-" * 80)
print("6. GOVERNMENT CONTRACTS COVERAGE")
print("-" * 80)
audit_field("Has ny_state_contracts > 0", "m.ny_state_contracts IS NOT NULL AND m.ny_state_contracts > 0")
audit_field("Has nyc_contracts > 0", "m.nyc_contracts IS NOT NULL AND m.nyc_contracts > 0")
audit_field("Has ANY state/city contract",
            "(m.ny_state_contracts IS NOT NULL AND m.ny_state_contracts > 0) OR "
            "(m.nyc_contracts IS NOT NULL AND m.nyc_contracts > 0)")

# Federal contractors via crosswalk
cur.execute("""
    SELECT
        COUNT(DISTINCT m.id) AS total,
        COUNT(DISTINCT m.id) FILTER (WHERE m.has_union = TRUE) AS u,
        COUNT(DISTINCT m.id) FILTER (WHERE m.has_union IS NOT TRUE) AS nu
    FROM mergent_employers m
    JOIN corporate_identifier_crosswalk cic ON cic.mergent_duns = m.duns
    WHERE cic.is_federal_contractor = TRUE
""")
row = cur.fetchone()
pct_t = 100*row[0]/total if total else 0
pct_u = 100*row[1]/union_count if union_count else 0
pct_nu = 100*row[2]/nonunion_count if nonunion_count else 0
print(f"  {'Federal contractor (via crosswalk)':42s}  {row[0]:>7,} ({pct_t:5.1f}%)   "
      f"U: {row[1]:>6,} ({pct_u:5.1f}%)   "
      f"NU: {row[2]:>6,} ({pct_nu:5.1f}%)")

audit_field("Has ANY govt contract (state/city/fed)",
            "(m.ny_state_contracts IS NOT NULL AND m.ny_state_contracts > 0) OR "
            "(m.nyc_contracts IS NOT NULL AND m.nyc_contracts > 0) OR "
            "EXISTS (SELECT 1 FROM corporate_identifier_crosswalk cic "
            "WHERE cic.mergent_duns = m.duns AND cic.is_federal_contractor = TRUE)")

# ============================================================
# SECTION 7: UNION STATUS
# ============================================================
print("\n" + "-" * 80)
print("7. UNION STATUS / F7 LINKAGE")
print("-" * 80)
audit_field("has_union = TRUE", "m.has_union = TRUE")
audit_field("Has matched_f7_employer_id", "m.matched_f7_employer_id IS NOT NULL")
audit_field("Has f7_union_name", "m.f7_union_name IS NOT NULL")
audit_field("Has sibling_union_bonus > 0", "m.sibling_union_bonus IS NOT NULL AND m.sibling_union_bonus > 0")

# ============================================================
# SECTION 8: NLRB
# ============================================================
print("\n" + "-" * 80)
print("8. NLRB COVERAGE")
print("-" * 80)
audit_field("Has nlrb_case_number", "m.nlrb_case_number IS NOT NULL")
audit_field("Has nlrb_election_date", "m.nlrb_election_date IS NOT NULL")
audit_field("nlrb_union_won = TRUE", "m.nlrb_union_won = TRUE")
audit_field("nlrb_union_won = FALSE", "m.nlrb_union_won = FALSE")

# ============================================================
# SECTION 9: LABOR VIOLATIONS (WHD + NYC)
# ============================================================
print("\n" + "-" * 80)
print("9. LABOR VIOLATIONS (WHD + NYC)")
print("-" * 80)
audit_field("Has whd_violation_count > 0", "m.whd_violation_count IS NOT NULL AND m.whd_violation_count > 0")
audit_field("Has whd_backwages > 0", "m.whd_backwages IS NOT NULL AND m.whd_backwages > 0")
audit_field("Has whd_repeat_violator", "m.whd_repeat_violator = TRUE")
audit_field("Has nyc_wage_theft_cases > 0", "m.nyc_wage_theft_cases IS NOT NULL AND m.nyc_wage_theft_cases > 0")
audit_field("Has nyc_ulp_cases > 0", "m.nyc_ulp_cases IS NOT NULL AND m.nyc_ulp_cases > 0")
audit_field("Has nyc_local_law_cases > 0", "m.nyc_local_law_cases IS NOT NULL AND m.nyc_local_law_cases > 0")
audit_field("Has nyc_debarred = TRUE", "m.nyc_debarred = TRUE")
audit_field("Has ANY labor violation",
            "(m.whd_violation_count IS NOT NULL AND m.whd_violation_count > 0) OR "
            "(m.nyc_wage_theft_cases IS NOT NULL AND m.nyc_wage_theft_cases > 0) OR "
            "(m.nyc_ulp_cases IS NOT NULL AND m.nyc_ulp_cases > 0) OR "
            "(m.nyc_local_law_cases IS NOT NULL AND m.nyc_local_law_cases > 0) OR "
            "(m.osha_violation_count IS NOT NULL AND m.osha_violation_count > 0)")

# ============================================================
# SECTION 10: CORPORATE HIERARCHY
# ============================================================
print("\n" + "-" * 80)
print("10. CORPORATE HIERARCHY / CROSSWALK")
print("-" * 80)
audit_field("Has parent_duns", "m.parent_duns IS NOT NULL")
audit_field("Has domestic_parent_duns", "m.domestic_parent_duns IS NOT NULL")
audit_field("Has global_duns", "m.global_duns IS NOT NULL")

# Crosswalk linkage
cur.execute("""
    SELECT
        COUNT(DISTINCT m.id) AS total,
        COUNT(DISTINCT m.id) FILTER (WHERE m.has_union = TRUE) AS u,
        COUNT(DISTINCT m.id) FILTER (WHERE m.has_union IS NOT TRUE) AS nu
    FROM mergent_employers m
    JOIN corporate_identifier_crosswalk cic ON cic.mergent_duns = m.duns
""")
row = cur.fetchone()
pct_t = 100*row[0]/total if total else 0
pct_u = 100*row[1]/union_count if union_count else 0
pct_nu = 100*row[2]/nonunion_count if nonunion_count else 0
print(f"  {'In crosswalk (has mergent_duns match)':42s}  {row[0]:>7,} ({pct_t:5.1f}%)   "
      f"U: {row[1]:>6,} ({pct_u:5.1f}%)   "
      f"NU: {row[2]:>6,} ({pct_nu:5.1f}%)")

# Crosswalk detail
cur.execute("""
    SELECT
        COUNT(DISTINCT m.id) FILTER (WHERE cic.gleif_lei IS NOT NULL) AS has_lei,
        COUNT(DISTINCT m.id) FILTER (WHERE cic.sec_cik IS NOT NULL) AS has_sec,
        COUNT(DISTINCT m.id) FILTER (WHERE cic.ein IS NOT NULL) AS has_ein,
        COUNT(DISTINCT m.id) FILTER (WHERE cic.is_public = TRUE) AS is_public
    FROM mergent_employers m
    JOIN corporate_identifier_crosswalk cic ON cic.mergent_duns = m.duns
""")
row = cur.fetchone()
print(f"\n  Crosswalk detail (of those in crosswalk):")
print(f"    Has GLEIF LEI:   {row[0]:>6,}")
print(f"    Has SEC CIK:     {row[1]:>6,}")
print(f"    Has EIN:         {row[2]:>6,}")
print(f"    Is public co:    {row[3]:>6,}")

audit_field("Has year_founded", "m.year_founded IS NOT NULL")
audit_field("Has company_type", "m.company_type IS NOT NULL")
audit_field("Has subsidiary_status", "m.subsidiary_status IS NOT NULL")

# ============================================================
# SECTION 11: MULTI-DIMENSIONAL RICHNESS
# ============================================================
print("\n" + "=" * 80)
print("11. MULTI-DIMENSIONAL RICHNESS ANALYSIS")
print("=" * 80)

cur.execute("""
    WITH dim_counts AS (
        SELECT
            m.id,
            m.has_union,
            -- Count how many dimensions have data
            (CASE WHEN m.naics_primary IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) IS NOT NULL
                  AND COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) > 0 THEN 1 ELSE 0 END) +
            (CASE WHEN COALESCE(m.sales_amount, m.ny990_revenue) IS NOT NULL
                  AND COALESCE(m.sales_amount, m.ny990_revenue) > 0 THEN 1 ELSE 0 END) +
            (CASE WHEN m.state IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN m.osha_violation_count IS NOT NULL AND m.osha_violation_count > 0 THEN 1 ELSE 0 END) +
            (CASE WHEN (m.ny_state_contracts IS NOT NULL AND m.ny_state_contracts > 0) OR
                       (m.nyc_contracts IS NOT NULL AND m.nyc_contracts > 0) THEN 1 ELSE 0 END) +
            (CASE WHEN m.has_union = TRUE THEN 1 ELSE 0 END) +
            (CASE WHEN m.nlrb_case_number IS NOT NULL THEN 1 ELSE 0 END) +
            (CASE WHEN (m.whd_violation_count IS NOT NULL AND m.whd_violation_count > 0) OR
                       (m.nyc_wage_theft_cases IS NOT NULL AND m.nyc_wage_theft_cases > 0) OR
                       (m.nyc_ulp_cases IS NOT NULL AND m.nyc_ulp_cases > 0) THEN 1 ELSE 0 END) +
            (CASE WHEN m.parent_duns IS NOT NULL OR m.domestic_parent_duns IS NOT NULL THEN 1 ELSE 0 END)
            AS dim_count
        FROM mergent_employers m
    )
    SELECT
        dim_count,
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM dim_counts
    GROUP BY dim_count
    ORDER BY dim_count
""")
print("\n  Dimensions with data (out of 10 max):")
print(f"    {'Dims':6s} {'Total':>8s} {'Union':>8s} {'Non-Un':>8s}  {'Cum Total':>10s}  {'Cum U':>8s}  {'Cum NU':>8s}")

rows = cur.fetchall()
cum_total, cum_u, cum_nu = 0, 0, 0
# We want "at least N dims" so accumulate from top
totals_by_dim = {}
for row in rows:
    totals_by_dim[row[0]] = (row[1], row[2], row[3])

# Print raw distribution
for dim in sorted(totals_by_dim.keys()):
    t, u, nu = totals_by_dim[dim]
    print(f"    {dim:>4d}   {t:>8,} {u:>8,} {nu:>8,}")

# "At least N" cumulative from top
print(f"\n  'At least N dimensions' cumulative:")
print(f"    {'>=N':6s} {'Total':>8s} {'%Total':>8s} {'Union':>8s} {'%Union':>8s} {'Non-Un':>8s} {'%NU':>8s}")
for threshold in range(0, 11):
    at_least_t = sum(v[0] for k, v in totals_by_dim.items() if k >= threshold)
    at_least_u = sum(v[1] for k, v in totals_by_dim.items() if k >= threshold)
    at_least_nu = sum(v[2] for k, v in totals_by_dim.items() if k >= threshold)
    pct_t = 100*at_least_t/total if total else 0
    pct_u = 100*at_least_u/union_count if union_count else 0
    pct_nu = 100*at_least_nu/nonunion_count if nonunion_count else 0
    marker = " <--" if threshold in (3, 5) else ""
    print(f"    >={threshold:>2d}   {at_least_t:>8,} {pct_t:>7.1f}% {at_least_u:>8,} {pct_u:>7.1f}% "
          f"{at_least_nu:>8,} {pct_nu:>7.1f}%{marker}")

# ============================================================
# SECTION 12: CROSS-DIMENSION OVERLAP (Union vs Non-Union)
# ============================================================
print("\n" + "=" * 80)
print("12. KEY OVERLAP ANALYSIS: Shared dimensions between Union and Non-Union")
print("=" * 80)

dimensions = [
    ("NAICS", "m.naics_primary IS NOT NULL"),
    ("Employees", "(COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) IS NOT NULL AND COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) > 0)"),
    ("Revenue", "(COALESCE(m.sales_amount, m.ny990_revenue) IS NOT NULL AND COALESCE(m.sales_amount, m.ny990_revenue) > 0)"),
    ("State", "m.state IS NOT NULL"),
    ("OSHA viol.", "(m.osha_violation_count IS NOT NULL AND m.osha_violation_count > 0)"),
    ("Govt contracts", "((m.ny_state_contracts > 0) OR (m.nyc_contracts > 0))"),
    ("NLRB", "m.nlrb_case_number IS NOT NULL"),
    ("Labor viol.", "((m.whd_violation_count > 0) OR (m.nyc_wage_theft_cases > 0) OR (m.nyc_ulp_cases > 0))"),
    ("Corp hierarchy", "(m.parent_duns IS NOT NULL OR m.domestic_parent_duns IS NOT NULL)"),
    ("Year founded", "m.year_founded IS NOT NULL"),
    ("Company type", "m.company_type IS NOT NULL"),
]

print(f"\n  For each dimension, how many union AND non-union employers both have data?")
print(f"  (Both groups need data in same dimension for Gower to compare them)\n")
print(f"  {'Dimension':18s} {'Union w/data':>14s} {'NonUn w/data':>14s} {'Both have':>10s}")
print(f"  {'-'*18:18s} {'-'*14:14s} {'-'*14:14s} {'-'*10:10s}")

for name, where in dimensions:
    cur.execute(f"""
        SELECT
            COUNT(*) FILTER (WHERE m.has_union = TRUE AND ({where})) AS u,
            COUNT(*) FILTER (WHERE m.has_union IS NOT TRUE AND ({where})) AS nu
        FROM mergent_employers m
    """)
    u, nu = cur.fetchone()
    both = "YES" if u > 0 and nu > 0 else "NO"
    print(f"  {name:18s} {u:>14,} {nu:>14,} {both:>10s}")

# ============================================================
# SECTION 13: PAIRWISE DIMENSION CO-OCCURRENCE
# ============================================================
print("\n" + "=" * 80)
print("13. PAIRWISE DIMENSION CO-OCCURRENCE (Non-Union targets only)")
print("=" * 80)
print("  How many non-union employers have BOTH dimensions populated?\n")

short_dims = [
    ("NAICS", "m.naics_primary IS NOT NULL"),
    ("Empl", "(COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) > 0)"),
    ("Rev", "(COALESCE(m.sales_amount, m.ny990_revenue) > 0)"),
    ("State", "m.state IS NOT NULL"),
    ("OSHA", "(m.osha_violation_count > 0)"),
    ("Contracts", "((m.ny_state_contracts > 0) OR (m.nyc_contracts > 0))"),
    ("LabViol", "((m.whd_violation_count > 0) OR (m.nyc_wage_theft_cases > 0))"),
    ("CorpHier", "(m.parent_duns IS NOT NULL)"),
]

# Print header
header = f"  {'':10s}"
for name, _ in short_dims:
    header += f" {name:>8s}"
print(header)

for i, (name_i, where_i) in enumerate(short_dims):
    row_str = f"  {name_i:10s}"
    for j, (name_j, where_j) in enumerate(short_dims):
        if j < i:
            row_str += f" {'':>8s}"
        else:
            cur.execute(f"""
                SELECT COUNT(*)
                FROM mergent_employers m
                WHERE m.has_union IS NOT TRUE
                  AND ({where_i})
                  AND ({where_j})
            """)
            cnt = cur.fetchone()[0]
            if cnt >= 1000:
                row_str += f" {cnt:>7,}k"[:-1]  # hack
            row_str += f" {cnt:>8,}"
    print(row_str)

# ============================================================
# SECTION 14: GOWER-READY ASSESSMENT
# ============================================================
print("\n" + "=" * 80)
print("14. GOWER-READY ASSESSMENT SUMMARY")
print("=" * 80)

# Count employers with the "core" dimensions for Gower
cur.execute("""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM mergent_employers m
    WHERE m.naics_primary IS NOT NULL
      AND m.state IS NOT NULL
      AND (COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) > 0)
""")
row = cur.fetchone()
print(f"\n  CORE 3 (NAICS + State + Employees):")
print(f"    Total: {row[0]:>8,}   Union: {row[1]:>6,}   Non-Union: {row[2]:>6,}")

cur.execute("""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM mergent_employers m
    WHERE m.naics_primary IS NOT NULL
      AND m.state IS NOT NULL
      AND (COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) > 0)
      AND (COALESCE(m.sales_amount, m.ny990_revenue) > 0)
""")
row = cur.fetchone()
print(f"\n  CORE 4 (NAICS + State + Employees + Revenue):")
print(f"    Total: {row[0]:>8,}   Union: {row[1]:>6,}   Non-Union: {row[2]:>6,}")

cur.execute("""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu
    FROM mergent_employers m
    WHERE m.naics_primary IS NOT NULL
      AND m.state IS NOT NULL
      AND (COALESCE(m.employees_site, m.employees_all_sites, m.ny990_employees) > 0)
      AND (COALESCE(m.sales_amount, m.ny990_revenue) > 0)
      AND ((m.osha_violation_count > 0) OR (m.whd_violation_count > 0) OR
           (m.nyc_wage_theft_cases > 0) OR (m.ny_state_contracts > 0) OR (m.nyc_contracts > 0))
""")
row = cur.fetchone()
print(f"\n  CORE 4 + Any violation/contract signal:")
print(f"    Total: {row[0]:>8,}   Union: {row[1]:>6,}   Non-Union: {row[2]:>6,}")

# Top NAICS overlap
print(f"\n  NAICS sectors with both Union and Non-Union employers (for within-sector Gower):")
cur.execute("""
    SELECT LEFT(naics_primary, 2) AS sector,
           COUNT(*) FILTER (WHERE has_union = TRUE) AS u,
           COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS nu,
           COUNT(*) AS total
    FROM mergent_employers
    WHERE naics_primary IS NOT NULL
    GROUP BY LEFT(naics_primary, 2)
    HAVING COUNT(*) FILTER (WHERE has_union = TRUE) >= 10
       AND COUNT(*) FILTER (WHERE has_union IS NOT TRUE) >= 10
    ORDER BY total DESC
""")
print(f"    {'Sector':8s} {'Total':>8s} {'Union':>8s} {'Non-Un':>8s} {'U%':>6s}")
for row in cur:
    upct = f"{100*row[1]/(row[1]+row[2]):.1f}%"
    print(f"    {row[0]:8s} {row[3]:>8,} {row[1]:>8,} {row[2]:>8,} {upct:>6s}")

# ============================================================
# FINAL VERDICT
# ============================================================
print("\n" + "=" * 80)
print("15. DATA SUFFICIENCY VERDICT")
print("=" * 80)

# Quick stats for verdict
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE naics_primary IS NOT NULL AND state IS NOT NULL
            AND COALESCE(employees_site, employees_all_sites, ny990_employees) > 0
            AND has_union IS NOT TRUE) AS nu_core3,
        COUNT(*) FILTER (WHERE naics_primary IS NOT NULL AND state IS NOT NULL
            AND COALESCE(employees_site, employees_all_sites, ny990_employees) > 0
            AND has_union = TRUE) AS u_core3,
        COUNT(*) FILTER (WHERE has_union IS NOT TRUE) AS total_nu,
        COUNT(*) FILTER (WHERE has_union = TRUE) AS total_u
    FROM mergent_employers
""")
nu3, u3, tnu, tu = cur.fetchone()

print(f"""
  DIMENSION QUALITY TIERS:
    Tier 1 (Universal):   NAICS, State, City   -- near-complete coverage
    Tier 2 (Strong):      Employees, Revenue, Company type, Year founded -- 50-99%
    Tier 3 (Moderate):    Corp hierarchy (parent_duns) -- ~30-50%
    Tier 4 (Sparse):      OSHA, WHD, Contracts, NLRB, NYC violations -- <10%

  CORE COMPARISON SET (NAICS + State + Employees):
    Union reference:     {u3:>6,} / {tu:>6,} ({100*u3/tu:.1f}%)
    Non-union targets:   {nu3:>6,} / {tnu:>6,} ({100*nu3/tnu:.1f}%)

  RECOMMENDATION:
    Gower Distance is VIABLE with a TIERED approach:
    - Base features (always available): NAICS sector, state, city, employee count, revenue
    - Enrichment features (when available): OSHA, WHD, contracts, NLRB, corp hierarchy
    - Use partial-distance Gower (ignore missing dimensions per pair)
    - Weight Tier 1-2 features more heavily since they drive most comparisons
    - Sparse Tier 4 features act as BONUS discriminators, not primary similarity axes
""")

cur.close()
conn.close()
print("Audit complete.")
