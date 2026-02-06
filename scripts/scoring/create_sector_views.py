"""
Create sector-specific views for organizing targets
Similar to the museum views but for each major sector
"""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor()

print("=" * 70)
print("CREATING SECTOR VIEWS")
print("=" * 70)

# Get sectors with significant employer counts
cur.execute("""
    SELECT sector_category, COUNT(*) as total,
           SUM(CASE WHEN has_union THEN 1 ELSE 0 END) as unionized
    FROM mergent_employers
    WHERE sector_category IS NOT NULL
    GROUP BY sector_category
    HAVING COUNT(*) >= 100
    ORDER BY COUNT(*) DESC
""")

sectors = cur.fetchall()
print(f"Sectors with 100+ employers: {len(sectors)}")

for sector, total, unionized in sectors:
    sector_lower = sector.lower()
    print(f"\n[{sector}] - {total} employers, {unionized} unionized")

    # Create organizing targets view
    cur.execute(f"""
        DROP VIEW IF EXISTS v_{sector_lower}_organizing_targets CASCADE;
        CREATE VIEW v_{sector_lower}_organizing_targets AS
        SELECT
            id,
            duns,
            ein,
            company_name as employer_name,
            city,
            state,
            county,
            employees_site as employee_count,
            ny990_employees,
            COALESCE(employees_site, ny990_employees) as best_employee_count,
            naics_primary,
            naics_primary_desc as industry,
            -- Scores
            score_geographic,
            score_size,
            score_industry_density,
            score_nlrb_momentum,
            score_osha_violations,
            score_govt_contracts,
            score_labor_violations,
            sibling_union_bonus,
            organizing_score as total_score,
            score_priority as priority_tier,
            -- Contract data
            ny_state_contracts,
            ny_state_contract_value,
            nyc_contracts,
            nyc_contract_value,
            COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) as total_contract_value,
            -- OSHA data
            osha_violation_count,
            osha_total_penalties,
            osha_last_violation_date,
            -- Labor violations (NYC Comptroller)
            nyc_wage_theft_cases,
            nyc_wage_theft_amount,
            nyc_ulp_cases,
            nyc_local_law_cases,
            nyc_local_law_amount,
            nyc_debarred,
            -- Match info
            ny990_id,
            matched_f7_employer_id,
            nlrb_case_number,
            osha_establishment_id
        FROM mergent_employers
        WHERE sector_category = '{sector}'
          AND has_union IS NOT TRUE
        ORDER BY organizing_score DESC NULLS LAST, employees_site DESC NULLS LAST;
    """)
    print(f"  - Created v_{sector_lower}_organizing_targets")

    # Create target stats view
    cur.execute(f"""
        DROP VIEW IF EXISTS v_{sector_lower}_target_stats CASCADE;
        CREATE VIEW v_{sector_lower}_target_stats AS
        SELECT
            score_priority as priority_tier,
            COUNT(*) as target_count,
            SUM(COALESCE(employees_site, ny990_employees, 0)) as total_employees,
            ROUND(AVG(organizing_score), 1) as avg_score,
            MIN(organizing_score) as min_score,
            MAX(organizing_score) as max_score,
            SUM(COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0)) as total_contract_value
        FROM mergent_employers
        WHERE sector_category = '{sector}'
          AND has_union IS NOT TRUE
        GROUP BY score_priority
        ORDER BY CASE score_priority
            WHEN 'TOP' THEN 1
            WHEN 'HIGH' THEN 2
            WHEN 'MEDIUM' THEN 3
            WHEN 'LOW' THEN 4
        END;
    """)
    print(f"  - Created v_{sector_lower}_target_stats")

    # Create unionized reference view
    cur.execute(f"""
        DROP VIEW IF EXISTS v_{sector_lower}_unionized CASCADE;
        CREATE VIEW v_{sector_lower}_unionized AS
        SELECT
            id,
            duns,
            ein,
            company_name as employer_name,
            city,
            state,
            employees_site as employee_count,
            f7_union_name as union_name,
            f7_union_fnum as union_fnum,
            nlrb_case_number,
            nlrb_election_date,
            osha_union_status
        FROM mergent_employers
        WHERE sector_category = '{sector}'
          AND has_union = TRUE
        ORDER BY employees_site DESC NULLS LAST;
    """)
    print(f"  - Created v_{sector_lower}_unionized")

conn.commit()

# Summary
print("\n" + "=" * 70)
print("VIEW SUMMARY")
print("=" * 70)

for sector, total, unionized in sectors:
    sector_lower = sector.lower()
    cur.execute(f"SELECT COUNT(*) FROM v_{sector_lower}_organizing_targets")
    targets = cur.fetchone()[0]
    cur.execute(f"SELECT COUNT(*) FROM v_{sector_lower}_unionized")
    union_count = cur.fetchone()[0]
    print(f"{sector:<25} Targets: {targets:>6}  Unionized: {union_count:>4}")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("VIEWS CREATED SUCCESSFULLY")
print("=" * 70)
