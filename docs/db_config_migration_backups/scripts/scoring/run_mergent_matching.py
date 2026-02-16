import os
"""
Run matching pipeline for Mergent employers
Matches to 990, F-7, NLRB, OSHA, contracts, and violations
"""

import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()
conn.autocommit = False

print("=" * 70)
print("MERGENT EMPLOYER MATCHING PIPELINE")
print("=" * 70)

# =============================================================================
# STEP 1: Match to IRS 990 data
# =============================================================================
print("\n[1/7] Matching to IRS Form 990 data...")

# Match by EIN (exact)
cur.execute("""
    UPDATE mergent_employers m
    SET ny990_id = n.id,
        ny990_employees = n.total_employees,
        ny990_revenue = n.total_revenue,
        ny990_match_method = 'EIN'
    FROM ny_990_filers n
    WHERE m.ein = n.ein
      AND m.ein IS NOT NULL
      AND m.ny990_id IS NULL
""")
ein_matches = cur.rowcount
print(f"  - EIN matches: {ein_matches}")

# Match by normalized name + city
cur.execute("""
    UPDATE mergent_employers m
    SET ny990_id = n.id,
        ny990_employees = n.total_employees,
        ny990_revenue = n.total_revenue,
        ny990_match_method = 'NAME_CITY'
    FROM ny_990_filers n
    WHERE m.company_name_normalized = LOWER(n.name_normalized)
      AND UPPER(m.city) = UPPER(n.city)
      AND m.ny990_id IS NULL
      AND n.total_employees IS NOT NULL
""")
name_city_matches = cur.rowcount
print(f"  - Name+City matches: {name_city_matches}")

conn.commit()

# Check 990 match rate
cur.execute("""
    SELECT COUNT(*),
           COUNT(CASE WHEN ny990_id IS NOT NULL THEN 1 END) as matched
    FROM mergent_employers
    WHERE sector_category != 'MUSEUMS'
""")
total, matched = cur.fetchone()
print(f"  990 Match Rate: {matched}/{total} ({100*matched/total:.1f}%)")

# =============================================================================
# STEP 2: Match to F-7 Employers (Union Status)
# =============================================================================
print("\n[2/7] Matching to F-7 employers (union contracts)...")

# Match by normalized name + city
cur.execute("""
    UPDATE mergent_employers m
    SET matched_f7_employer_id = f.employer_id,
        f7_union_name = f.latest_union_name,
        f7_union_fnum = f.latest_union_fnum,
        f7_match_method = 'NAME_CITY',
        has_union = TRUE
    FROM f7_employers_deduped f
    WHERE m.company_name_normalized = LOWER(REGEXP_REPLACE(f.employer_name, '[^A-Za-z0-9 ]', '', 'g'))
      AND UPPER(m.city) = UPPER(f.city)
      AND m.matched_f7_employer_id IS NULL
""")
f7_name = cur.rowcount
print(f"  - Name+City matches: {f7_name}")

# Also match by aggressive name normalization
cur.execute("""
    UPDATE mergent_employers m
    SET matched_f7_employer_id = f.employer_id,
        f7_union_name = f.latest_union_name,
        f7_union_fnum = f.latest_union_fnum,
        f7_match_method = 'NAME_AGGRESSIVE',
        has_union = TRUE
    FROM f7_employers_deduped f
    WHERE m.company_name_normalized = f.employer_name_aggressive
      AND UPPER(m.city) = UPPER(f.city)
      AND m.matched_f7_employer_id IS NULL
      AND f.employer_name_aggressive IS NOT NULL
""")
f7_agg = cur.rowcount
print(f"  - Aggressive name matches: {f7_agg}")

conn.commit()

# =============================================================================
# STEP 3: Match to NLRB Elections
# =============================================================================
print("\n[3/7] Matching to NLRB elections...")

# Match by normalized name + city (join elections and participants)
cur.execute("""
    UPDATE mergent_employers m
    SET nlrb_case_number = e.case_number,
        nlrb_election_date = e.election_date,
        nlrb_union_won = e.union_won,
        nlrb_eligible_voters = e.eligible_voters,
        nlrb_match_method = 'NAME_CITY',
        has_union = CASE WHEN e.union_won THEN TRUE ELSE m.has_union END
    FROM nlrb_elections e
    JOIN nlrb_participants p ON e.case_number = p.case_number
    WHERE p.participant_type = 'Employer'
      AND m.company_name_normalized = LOWER(REGEXP_REPLACE(p.participant_name, '[^A-Za-z0-9 ]', '', 'g'))
      AND UPPER(m.city) = UPPER(p.city)
      AND m.nlrb_case_number IS NULL
""")
nlrb_matches = cur.rowcount
print(f"  - NLRB matches: {nlrb_matches}")

conn.commit()

# =============================================================================
# STEP 4: Match to OSHA Establishments
# =============================================================================
print("\n[4/7] Matching to OSHA establishments...")

# Match by normalized name + city
cur.execute("""
    WITH osha_agg AS (
        SELECT
            LOWER(REGEXP_REPLACE(estab_name, '[^A-Za-z0-9 ]', '', 'g')) as name_norm,
            UPPER(site_city) as city_norm,
            MIN(establishment_id) as estab_id,
            COUNT(*) as inspection_count,
            MAX(union_status) as union_status
        FROM osha_establishments
        WHERE estab_name IS NOT NULL
        GROUP BY 1, 2
    ),
    osha_viol AS (
        SELECT
            establishment_id,
            COUNT(*) as violation_count,
            SUM(current_penalty) as total_penalties,
            MAX(issuance_date) as last_date
        FROM osha_violations_detail
        GROUP BY establishment_id
    )
    UPDATE mergent_employers m
    SET osha_establishment_id = o.estab_id,
        osha_total_inspections = o.inspection_count,
        osha_union_status = o.union_status,
        osha_match_method = 'NAME_CITY',
        osha_violation_count = COALESCE(v.violation_count, 0),
        osha_total_penalties = COALESCE(v.total_penalties, 0),
        osha_last_violation_date = v.last_date,
        has_union = CASE WHEN o.union_status IN ('Y', 'A') THEN TRUE ELSE m.has_union END
    FROM osha_agg o
    LEFT JOIN osha_viol v ON o.estab_id = v.establishment_id
    WHERE m.company_name_normalized = o.name_norm
      AND UPPER(m.city) = o.city_norm
      AND m.osha_establishment_id IS NULL
""")
osha_matches = cur.rowcount
print(f"  - OSHA matches: {osha_matches}")

conn.commit()

# =============================================================================
# STEP 5: Match to Government Contracts
# =============================================================================
print("\n[5/7] Matching to government contracts...")

# Match NY State contracts by EIN
cur.execute("""
    WITH contract_agg AS (
        SELECT
            vendor_ein,
            COUNT(*) as contract_count,
            SUM(current_amount) as total_value
        FROM ny_state_contracts
        WHERE vendor_ein IS NOT NULL
        GROUP BY vendor_ein
    )
    UPDATE mergent_employers m
    SET ny_state_contracts = c.contract_count,
        ny_state_contract_value = c.total_value
    FROM contract_agg c
    WHERE m.ein = c.vendor_ein
      AND m.ein IS NOT NULL
      AND m.ny_state_contracts IS NULL
""")
ny_contracts = cur.rowcount
print(f"  - NY State contract matches (by EIN): {ny_contracts}")

# Also match NY State by normalized name
cur.execute("""
    WITH contract_agg AS (
        SELECT
            vendor_name_normalized,
            COUNT(*) as contract_count,
            SUM(current_amount) as total_value
        FROM ny_state_contracts
        WHERE vendor_name_normalized IS NOT NULL
        GROUP BY vendor_name_normalized
    )
    UPDATE mergent_employers m
    SET ny_state_contracts = c.contract_count,
        ny_state_contract_value = c.total_value
    FROM contract_agg c
    WHERE m.company_name_normalized = c.vendor_name_normalized
      AND m.ny_state_contracts IS NULL
""")
ny_contracts_name = cur.rowcount
print(f"  - NY State contract matches (by name): {ny_contracts_name}")

# Match NYC contracts by EIN
cur.execute("""
    WITH contract_agg AS (
        SELECT
            vendor_ein,
            COUNT(*) as contract_count,
            SUM(COALESCE(current_amount, original_amount)) as total_value
        FROM nyc_contracts
        WHERE vendor_ein IS NOT NULL
        GROUP BY vendor_ein
    )
    UPDATE mergent_employers m
    SET nyc_contracts = c.contract_count,
        nyc_contract_value = c.total_value
    FROM contract_agg c
    WHERE m.ein = c.vendor_ein
      AND m.ein IS NOT NULL
      AND m.nyc_contracts IS NULL
""")
nyc_contracts_ein = cur.rowcount
print(f"  - NYC contract matches (by EIN): {nyc_contracts_ein}")

# Match NYC contracts by normalized name
cur.execute("""
    WITH contract_agg AS (
        SELECT
            vendor_name_normalized,
            COUNT(*) as contract_count,
            SUM(COALESCE(current_amount, original_amount)) as total_value
        FROM nyc_contracts
        WHERE vendor_name_normalized IS NOT NULL
        GROUP BY vendor_name_normalized
    )
    UPDATE mergent_employers m
    SET nyc_contracts = c.contract_count,
        nyc_contract_value = c.total_value
    FROM contract_agg c
    WHERE m.company_name_normalized = c.vendor_name_normalized
      AND m.nyc_contracts IS NULL
""")
nyc_contracts = cur.rowcount
print(f"  - NYC contract matches (by name): {nyc_contracts}")

# Also match from organizing_targets table by EIN (has pre-aggregated data)
cur.execute("""
    UPDATE mergent_employers m
    SET ny_state_contracts = COALESCE(m.ny_state_contracts, 0) + COALESCE(t.ny_state_contract_count, 0),
        ny_state_contract_value = COALESCE(m.ny_state_contract_value, 0) + COALESCE(t.ny_state_contract_total, 0),
        nyc_contracts = COALESCE(m.nyc_contracts, 0) + COALESCE(t.nyc_contract_count, 0),
        nyc_contract_value = COALESCE(m.nyc_contract_value, 0) + COALESCE(t.nyc_contract_total, 0)
    FROM organizing_targets t
    WHERE m.ein = t.ein
      AND m.ein IS NOT NULL
      AND (t.ny_state_contract_count > 0 OR t.nyc_contract_count > 0)
      AND m.ny_state_contracts IS NULL
      AND m.nyc_contracts IS NULL
""")
targets_match = cur.rowcount
print(f"  - Organizing targets matches (by EIN): {targets_match}")

conn.commit()

# =============================================================================
# STEP 6: Match to Labor Violations (NYC Comptroller Data)
# =============================================================================
print("\n[6/7] Matching to labor violations...")

# Match NYC wage theft (NYS DOL) by normalized name + city
cur.execute("""
    WITH wage_agg AS (
        SELECT
            LOWER(REGEXP_REPLACE(employer_name, '[^A-Za-z0-9 ]', '', 'g')) as name_norm,
            UPPER(city) as city_norm,
            COUNT(*) as violation_count,
            SUM(wages_owed) as backwages,
            SUM(num_claimants) as employees_violated
        FROM nyc_wage_theft_nys
        WHERE employer_name IS NOT NULL
        GROUP BY 1, 2
    )
    UPDATE mergent_employers m
    SET whd_violation_count = w.violation_count,
        whd_backwages = w.backwages,
        whd_employees_violated = w.employees_violated,
        whd_match_method = 'NYS_DOL'
    FROM wage_agg w
    WHERE m.company_name_normalized = w.name_norm
      AND UPPER(m.city) = w.city_norm
      AND m.whd_violation_count IS NULL
""")
nys_dol_matches = cur.rowcount
print(f"  - NYS DOL wage theft matches: {nys_dol_matches}")

# Match NYC wage theft (US DOL) by normalized name + city
cur.execute("""
    WITH wage_agg AS (
        SELECT
            LOWER(REGEXP_REPLACE(trade_name, '[^A-Za-z0-9 ]', '', 'g')) as name_norm,
            UPPER(city) as city_norm,
            COUNT(*) as violation_count,
            SUM(backwages_amount) as backwages,
            SUM(employees_violated) as employees_violated
        FROM nyc_wage_theft_usdol
        WHERE trade_name IS NOT NULL
        GROUP BY 1, 2
    )
    UPDATE mergent_employers m
    SET whd_violation_count = COALESCE(m.whd_violation_count, 0) + w.violation_count,
        whd_backwages = COALESCE(m.whd_backwages, 0) + w.backwages,
        whd_employees_violated = COALESCE(m.whd_employees_violated, 0) + w.employees_violated,
        whd_match_method = LEFT(CASE WHEN m.whd_match_method IS NULL THEN 'US_DOL' ELSE m.whd_match_method || '+US_DOL' END, 20)
    FROM wage_agg w
    WHERE m.company_name_normalized = w.name_norm
      AND UPPER(m.city) = w.city_norm
""")
us_dol_matches = cur.rowcount
print(f"  - US DOL wage theft matches: {us_dol_matches}")

conn.commit()

# =============================================================================
# STEP 7: Calculate Scores
# =============================================================================
print("\n[7/7] Calculating organizing scores...")

# Score: Geographic (0-15)
cur.execute("""
    UPDATE mergent_employers
    SET score_geographic = CASE
        WHEN city IN ('NEW YORK', 'MANHATTAN', 'BROOKLYN', 'BRONX', 'QUEENS', 'STATEN ISLAND') THEN 15
        WHEN city IN ('ALBANY', 'BUFFALO', 'ROCHESTER', 'SYRACUSE', 'YONKERS') THEN 10
        ELSE 5
    END
""")
print("  - Geographic scores set")

# Score: Size (0-5)
cur.execute("""
    UPDATE mergent_employers
    SET score_size = CASE
        WHEN employees_site BETWEEN 100 AND 500 THEN 5
        WHEN employees_site BETWEEN 50 AND 99 THEN 4
        WHEN employees_site BETWEEN 25 AND 49 THEN 3
        WHEN employees_site BETWEEN 500 AND 1000 THEN 2
        WHEN employees_site > 1000 THEN 1
        ELSE 0
    END
""")
print("  - Size scores set")

# Score: Industry Density (0-5)
# Calculate unionization rate by sector
cur.execute("""
    WITH sector_density AS (
        SELECT sector_category,
               COUNT(*) as total,
               SUM(CASE WHEN has_union THEN 1 ELSE 0 END) as unionized,
               ROUND(100.0 * SUM(CASE WHEN has_union THEN 1 ELSE 0 END) / COUNT(*), 1) as pct
        FROM mergent_employers
        GROUP BY sector_category
    )
    UPDATE mergent_employers m
    SET score_industry_density = CASE
        WHEN s.pct >= 15 THEN 5
        WHEN s.pct >= 10 THEN 4
        WHEN s.pct >= 5 THEN 3
        WHEN s.pct >= 2 THEN 2
        ELSE 1
    END
    FROM sector_density s
    WHERE m.sector_category = s.sector_category
""")
print("  - Industry density scores set")

# Score: NLRB Momentum (0-5)
cur.execute("""
    WITH recent_wins AS (
        SELECT UPPER(p.city) as city_norm,
               COUNT(*) as wins
        FROM nlrb_elections e
        JOIN nlrb_participants p ON e.case_number = p.case_number
        WHERE e.union_won = true
          AND e.election_date >= '2022-01-01'
          AND p.participant_type = 'Employer'
        GROUP BY UPPER(p.city)
    )
    UPDATE mergent_employers m
    SET score_nlrb_momentum = CASE
        WHEN w.wins >= 5 THEN 5
        WHEN w.wins >= 3 THEN 4
        WHEN w.wins >= 1 THEN 3
        WHEN m.city IN ('NEW YORK', 'BROOKLYN', 'BRONX', 'QUEENS') THEN 2
        ELSE 0
    END
    FROM recent_wins w
    WHERE UPPER(m.city) = w.city_norm
""")
# Set default for non-matches
cur.execute("""
    UPDATE mergent_employers
    SET score_nlrb_momentum = CASE
        WHEN city IN ('NEW YORK', 'BROOKLYN', 'BRONX', 'QUEENS') THEN 2
        ELSE 0
    END
    WHERE score_nlrb_momentum IS NULL
""")
print("  - NLRB momentum scores set")

# Score: OSHA Violations (0-4)
cur.execute("""
    UPDATE mergent_employers
    SET score_osha_violations = CASE
        WHEN osha_violation_count >= 5 AND osha_last_violation_date >= '2022-01-01' THEN 4
        WHEN osha_violation_count >= 3 OR osha_last_violation_date >= '2022-01-01' THEN 3
        WHEN osha_violation_count >= 1 THEN 2
        ELSE 0
    END
""")
print("  - OSHA violation scores set")

# Score: Government Contracts (0-15)
cur.execute("""
    UPDATE mergent_employers
    SET score_govt_contracts = CASE
        WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 5000000 THEN 15
        WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 1000000 THEN 12
        WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 500000 THEN 10
        WHEN COALESCE(ny_state_contract_value, 0) + COALESCE(nyc_contract_value, 0) >= 100000 THEN 7
        WHEN COALESCE(ny_state_contracts, 0) + COALESCE(nyc_contracts, 0) >= 1 THEN 4
        ELSE 0
    END
""")
print("  - Government contract scores set")

# Sibling union bonus (0-8) - two methods:
# 1. Same parent company has a unionized location
# 2. Name matches an F-7 employer at a different address

# First, clear any existing sibling bonuses
cur.execute("""
    UPDATE mergent_employers
    SET sibling_union_bonus = 0,
        sibling_union_note = NULL
""")

# Method 1: Parent company match
cur.execute("""
    WITH unionized_parents AS (
        SELECT DISTINCT parent_duns, parent_name
        FROM mergent_employers
        WHERE has_union = TRUE
          AND parent_duns IS NOT NULL
    )
    UPDATE mergent_employers m
    SET sibling_union_bonus = 8,
        sibling_union_note = CONCAT('Parent company (', u.parent_name, ') has unionized location')
    FROM unionized_parents u
    WHERE m.parent_duns = u.parent_duns
      AND m.has_union IS NOT TRUE
""")
parent_matches = cur.rowcount
print(f"  - Sibling bonus (parent company): {parent_matches}")

# Method 2: Name match with F-7 at different address
cur.execute("""
    WITH f7_unionized AS (
        SELECT DISTINCT
            employer_name_aggressive,
            employer_name,
            street,
            city,
            latest_union_name
        FROM f7_employers_deduped
        WHERE latest_union_name IS NOT NULL
    )
    UPDATE mergent_employers m
    SET sibling_union_bonus = 8,
        sibling_union_note = CONCAT('Same org has union at different location: ', f.employer_name, ' (', f.latest_union_name, ')')
    FROM f7_unionized f
    WHERE LOWER(m.company_name_normalized) = LOWER(f.employer_name_aggressive)
      AND m.has_union IS NOT TRUE
      AND m.sibling_union_bonus = 0
      AND (
          UPPER(COALESCE(m.street_address, '')) != UPPER(COALESCE(f.street, ''))
          OR UPPER(COALESCE(m.city, '')) != UPPER(COALESCE(f.city, ''))
      )
""")
name_matches = cur.rowcount
print(f"  - Sibling bonus (name match, different address): {name_matches}")

# Calculate total organizing score (non-union only)
cur.execute("""
    UPDATE mergent_employers
    SET organizing_score = COALESCE(score_geographic, 0)
                         + COALESCE(score_size, 0)
                         + COALESCE(score_industry_density, 0)
                         + COALESCE(score_nlrb_momentum, 0)
                         + COALESCE(score_osha_violations, 0)
                         + COALESCE(score_govt_contracts, 0)
                         + COALESCE(sibling_union_bonus, 0)
    WHERE has_union IS NOT TRUE
""")
cur.execute("""
    UPDATE mergent_employers
    SET organizing_score = NULL
    WHERE has_union = TRUE
""")
print("  - Total organizing scores calculated")

# Set priority tier
cur.execute("""
    UPDATE mergent_employers
    SET score_priority = CASE
        WHEN organizing_score >= 40 THEN 'TOP'
        WHEN organizing_score >= 30 THEN 'HIGH'
        WHEN organizing_score >= 20 THEN 'MEDIUM'
        ELSE 'LOW'
    END
    WHERE has_union IS NOT TRUE
""")
print("  - Priority tiers set")

conn.commit()

# =============================================================================
# Summary
# =============================================================================
print("\n" + "=" * 70)
print("MATCHING SUMMARY")
print("=" * 70)

cur.execute("""
    SELECT
        sector_category,
        COUNT(*) as total,
        SUM(CASE WHEN has_union THEN 1 ELSE 0 END) as unionized,
        SUM(CASE WHEN ny990_id IS NOT NULL THEN 1 ELSE 0 END) as matched_990,
        SUM(CASE WHEN matched_f7_employer_id IS NOT NULL THEN 1 ELSE 0 END) as matched_f7,
        SUM(CASE WHEN nlrb_case_number IS NOT NULL THEN 1 ELSE 0 END) as matched_nlrb,
        SUM(CASE WHEN osha_establishment_id IS NOT NULL THEN 1 ELSE 0 END) as matched_osha,
        SUM(CASE WHEN COALESCE(ny_state_contracts, 0) + COALESCE(nyc_contracts, 0) > 0 THEN 1 ELSE 0 END) as has_contracts,
        AVG(organizing_score) FILTER (WHERE has_union IS NOT TRUE) as avg_score
    FROM mergent_employers
    GROUP BY sector_category
    ORDER BY COUNT(*) DESC
""")

print(f"\n{'Sector':<22} {'Total':>6} {'Union':>6} {'990':>6} {'F-7':>6} {'NLRB':>6} {'OSHA':>6} {'Contr':>6} {'AvgScr':>7}")
print("-" * 80)
for row in cur.fetchall():
    avg = f"{row[8]:.1f}" if row[8] else "N/A"
    print(f"{row[0] or 'NULL':<22} {row[1]:>6} {row[2]:>6} {row[3]:>6} {row[4]:>6} {row[5]:>6} {row[6]:>6} {row[7]:>6} {avg:>7}")

# Priority tier breakdown
print("\n" + "=" * 70)
print("PRIORITY TIER BREAKDOWN (Non-Union Targets)")
print("=" * 70)

cur.execute("""
    SELECT
        sector_category,
        score_priority,
        COUNT(*) as count,
        SUM(employees_site) as employees
    FROM mergent_employers
    WHERE has_union IS NOT TRUE
    GROUP BY sector_category, score_priority
    ORDER BY sector_category,
             CASE score_priority WHEN 'TOP' THEN 1 WHEN 'HIGH' THEN 2 WHEN 'MEDIUM' THEN 3 ELSE 4 END
""")

results = {}
for row in cur.fetchall():
    sector = row[0]
    tier = row[1]
    if sector not in results:
        results[sector] = {}
    results[sector][tier] = {'count': row[2], 'emp': row[3] or 0}

print(f"\n{'Sector':<22} {'TOP':>8} {'HIGH':>8} {'MEDIUM':>10} {'LOW':>8}")
print("-" * 60)
for sector in results:
    top = results[sector].get('TOP', {}).get('count', 0)
    high = results[sector].get('HIGH', {}).get('count', 0)
    med = results[sector].get('MEDIUM', {}).get('count', 0)
    low = results[sector].get('LOW', {}).get('count', 0)
    print(f"{sector:<22} {top:>8} {high:>8} {med:>10} {low:>8}")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("MATCHING COMPLETE")
print("=" * 70)
