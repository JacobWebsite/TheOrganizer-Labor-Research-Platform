import os
"""
VR Integration Views - Checkpoint 5A
Core VR views with matched employer/union data
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
conn.autocommit = True
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("VR Integration Views - Checkpoint 5A: Core Views")
print("=" * 60)

# View 1: Full VR cases with matched data
print("\n--- Creating v_vr_cases_full ---")
cur.execute("""
    DROP VIEW IF EXISTS v_vr_cases_full CASCADE;
    CREATE VIEW v_vr_cases_full AS
    SELECT 
        vr.id,
        vr.vr_case_number,
        vr.region,
        nr.region_name,
        vr.unit_city,
        vr.unit_state,
        vr.date_vr_request_received,
        vr.date_voluntary_recognition,
        vr.date_vr_notice_sent,
        vr.date_posting_closes,
        
        -- Employer info
        vr.employer_name,
        vr.employer_name_normalized,
        vr.matched_employer_id,
        vr.employer_match_confidence,
        vr.employer_match_method,
        f7.employer_name as f7_employer_name,
        f7.city as f7_city,
        f7.state as f7_state,
        f7.naics as f7_naics,
        f7.latitude as f7_latitude,
        f7.longitude as f7_longitude,
        
        -- Union info
        vr.union_name,
        vr.extracted_affiliation,
        vr.extracted_local_number,
        vr.matched_union_fnum,
        vr.union_match_confidence,
        vr.union_match_method,
        um.union_name as olms_union_name,
        um.aff_abbr as olms_aff_abbr,
        um.members as olms_members,
        um.city as olms_city,
        um.state as olms_state,
        
        -- Unit details
        vr.unit_description,
        vr.num_employees,
        
        -- Linkages
        vr.r_case_number,
        vr.notes,
        
        -- Derived
        EXTRACT(YEAR FROM vr.date_vr_request_received)::int as request_year,
        CASE 
            WHEN vr.matched_employer_id IS NOT NULL AND vr.matched_union_fnum IS NOT NULL THEN 'fully_linked'
            WHEN vr.matched_employer_id IS NOT NULL THEN 'employer_only'
            WHEN vr.matched_union_fnum IS NOT NULL THEN 'union_only'
            ELSE 'unlinked'
        END as link_status
        
    FROM nlrb_voluntary_recognition vr
    LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    LEFT JOIN unions_master um ON vr.matched_union_fnum = um.f_num
    LEFT JOIN nlrb_regions nr ON vr.region = nr.region_number
""")
print("  Created v_vr_cases_full")

# View 2: VR with geocoding (use F7 coords or derive from city)
print("\n--- Creating v_vr_map_data ---")
cur.execute("""
    DROP VIEW IF EXISTS v_vr_map_data CASCADE;
    CREATE VIEW v_vr_map_data AS
    SELECT 
        vr.id,
        vr.vr_case_number,
        vr.employer_name_normalized as employer_name,
        vr.unit_city as city,
        vr.unit_state as state,
        vr.extracted_affiliation as affiliation,
        vr.num_employees,
        vr.date_vr_request_received,
        EXTRACT(YEAR FROM vr.date_vr_request_received)::int as year,
        -- Use F7 coordinates if matched, otherwise NULL
        f7.latitude,
        f7.longitude,
        CASE WHEN f7.latitude IS NOT NULL THEN true ELSE false END as has_coordinates,
        vr.matched_employer_id IS NOT NULL as employer_matched,
        vr.matched_union_fnum IS NOT NULL as union_matched
    FROM nlrb_voluntary_recognition vr
    LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    WHERE vr.unit_state IS NOT NULL
""")
print("  Created v_vr_map_data")

# View 3: Updated v_vr_by_year with more details
print("\n--- Updating v_vr_by_year ---")
cur.execute("""
    DROP VIEW IF EXISTS v_vr_by_year CASCADE;
    CREATE VIEW v_vr_by_year AS
    SELECT 
        EXTRACT(YEAR FROM date_vr_request_received)::int as year,
        COUNT(*) as total_cases,
        SUM(COALESCE(num_employees, 0)) as total_employees,
        AVG(num_employees)::int as avg_unit_size,
        COUNT(DISTINCT unit_state) as states_covered,
        COUNT(CASE WHEN r_case_number IS NOT NULL THEN 1 END) as petitions_filed,
        COUNT(matched_employer_id) as employers_matched,
        COUNT(matched_union_fnum) as unions_matched,
        ROUND(100.0 * COUNT(matched_employer_id) / COUNT(*), 1) as employer_match_pct,
        ROUND(100.0 * COUNT(matched_union_fnum) / COUNT(*), 1) as union_match_pct
    FROM nlrb_voluntary_recognition
    WHERE date_vr_request_received IS NOT NULL
    GROUP BY EXTRACT(YEAR FROM date_vr_request_received)
    ORDER BY year
""")
print("  Updated v_vr_by_year")

# View 4: Updated v_vr_by_state with more details
print("\n--- Updating v_vr_by_state ---")
cur.execute("""
    DROP VIEW IF EXISTS v_vr_by_state CASCADE;
    CREATE VIEW v_vr_by_state AS
    SELECT 
        unit_state as state,
        COUNT(*) as total_cases,
        SUM(COALESCE(num_employees, 0)) as total_employees,
        AVG(num_employees)::int as avg_unit_size,
        COUNT(matched_employer_id) as employers_matched,
        COUNT(matched_union_fnum) as unions_matched,
        COUNT(DISTINCT extracted_affiliation) as unique_affiliations,
        MIN(date_vr_request_received) as earliest_case,
        MAX(date_vr_request_received) as latest_case
    FROM nlrb_voluntary_recognition
    WHERE unit_state IS NOT NULL AND LENGTH(unit_state) = 2
    GROUP BY unit_state
    ORDER BY COUNT(*) DESC
""")
print("  Updated v_vr_by_state")

# View 5: Updated v_vr_by_affiliation with OLMS linkage
print("\n--- Updating v_vr_by_affiliation ---")
cur.execute("""
    DROP VIEW IF EXISTS v_vr_by_affiliation CASCADE;
    CREATE VIEW v_vr_by_affiliation AS
    SELECT 
        vr.extracted_affiliation as affiliation,
        COUNT(*) as total_cases,
        SUM(COALESCE(vr.num_employees, 0)) as total_employees,
        AVG(vr.num_employees)::int as avg_unit_size,
        COUNT(vr.matched_union_fnum) as unions_matched,
        COUNT(DISTINCT vr.matched_union_fnum) as unique_locals_matched,
        ROUND(100.0 * COUNT(vr.matched_union_fnum) / COUNT(*), 1) as match_rate,
        MIN(vr.date_vr_request_received) as earliest_case,
        MAX(vr.date_vr_request_received) as latest_case,
        -- Aggregate OLMS data
        SUM(DISTINCT COALESCE(um.members, 0)) as olms_total_members
    FROM nlrb_voluntary_recognition vr
    LEFT JOIN unions_master um ON vr.matched_union_fnum = um.f_num
    GROUP BY vr.extracted_affiliation
    ORDER BY COUNT(*) DESC
""")
print("  Updated v_vr_by_affiliation")

# View 6: VR employer pipeline (employers that got VR then appear in F7)
print("\n--- Creating v_vr_employer_pipeline ---")
cur.execute("""
    DROP VIEW IF EXISTS v_vr_employer_pipeline CASCADE;
    CREATE VIEW v_vr_employer_pipeline AS
    SELECT 
        vr.id as vr_id,
        vr.vr_case_number,
        vr.employer_name_normalized as vr_employer,
        vr.date_vr_request_received as vr_date,
        vr.num_employees as vr_employees,
        vr.extracted_affiliation,
        f7.employer_id,
        f7.employer_name as f7_employer,
        f7.latest_notice_date as f7_date,
        f7.latest_unit_size as f7_employees,
        f7.latest_union_name as f7_union,
        -- Calculate time from VR to F7 filing
        f7.latest_notice_date - vr.date_vr_request_received as days_to_f7,
        CASE 
            WHEN f7.latest_notice_date > vr.date_vr_request_received THEN 'vr_then_f7'
            WHEN f7.latest_notice_date < vr.date_vr_request_received THEN 'f7_then_vr'
            ELSE 'same_period'
        END as sequence
    FROM nlrb_voluntary_recognition vr
    JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    WHERE vr.date_vr_request_received IS NOT NULL
      AND f7.latest_notice_date IS NOT NULL
    ORDER BY vr.date_vr_request_received DESC
""")
print("  Created v_vr_employer_pipeline")

# Verify views
print("\n--- Verifying views ---")
views = [
    'v_vr_cases_full',
    'v_vr_map_data', 
    'v_vr_by_year',
    'v_vr_by_state',
    'v_vr_by_affiliation',
    'v_vr_employer_pipeline'
]

for view in views:
    cur.execute(f"SELECT COUNT(*) as cnt FROM {view}")
    cnt = cur.fetchone()['cnt']
    print(f"  {view}: {cnt} rows")

cur.close()
conn.close()

print(f"\n{'=' * 60}")
print("CHECKPOINT 5A COMPLETE - Core VR views created")
print("Ready for 5B: Cross-dataset integration views")
print(f"{'=' * 60}")
