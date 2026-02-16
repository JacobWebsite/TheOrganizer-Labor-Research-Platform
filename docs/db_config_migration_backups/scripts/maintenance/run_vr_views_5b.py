import os
"""
Run VR Views 5B SQL - Fixed version
"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
conn.autocommit = True
cur = conn.cursor()

print("=" * 60)
print("VR Integration Views - Checkpoint 5B")
print("=" * 60)

# Execute each view creation separately
views_sql = {
    'v_all_organizing_events': """
        DROP VIEW IF EXISTS v_all_organizing_events CASCADE;
        CREATE OR REPLACE VIEW v_all_organizing_events AS
        SELECT 
            'election' as event_type,
            c.case_number,
            emp.participant_name as employer_name,
            emp.city,
            emp.state,
            e.election_date as event_date,
            EXTRACT(YEAR FROM e.election_date)::int as event_year,
            uni.participant_name as union_name,
            NULL::text as union_affiliation,
            e.eligible_voters as num_employees,
            c.case_type,
            CASE WHEN e.union_won THEN 'WON' ELSE 'LOST' END as outcome,
            e.union_won::text as union_won,
            NULL::float as latitude,
            NULL::float as longitude,
            emp.matched_employer_id,
            uni.matched_olms_fnum as matched_union_fnum
        FROM nlrb_elections e
        JOIN nlrb_cases c ON e.case_number = c.case_number
        LEFT JOIN nlrb_participants emp ON c.case_number = emp.case_number 
            AND emp.participant_type = 'Employer'
        LEFT JOIN nlrb_participants uni ON c.case_number = uni.case_number 
            AND uni.participant_type IN ('Labor Organization', 'Union', 'Petitioner')
            AND uni.participant_name NOT LIKE '%Employer%'
        WHERE e.election_date IS NOT NULL

        UNION ALL

        SELECT 
            'voluntary_recognition' as event_type,
            vr.vr_case_number as case_number,
            vr.employer_name_normalized as employer_name,
            vr.unit_city as city,
            vr.unit_state as state,
            vr.date_vr_request_received as event_date,
            EXTRACT(YEAR FROM vr.date_vr_request_received)::int as event_year,
            vr.union_name_normalized as union_name,
            vr.extracted_affiliation as union_affiliation,
            vr.num_employees,
            'VR' as case_type,
            CASE WHEN vr.date_voluntary_recognition IS NOT NULL THEN 'RECOGNIZED' ELSE 'PENDING' END as outcome,
            'true' as union_won,
            f7.latitude,
            f7.longitude,
            vr.matched_employer_id,
            vr.matched_union_fnum
        FROM nlrb_voluntary_recognition vr
        LEFT JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
        WHERE vr.date_vr_request_received IS NOT NULL
    """,
    
    'v_organizing_by_year': """
        DROP VIEW IF EXISTS v_organizing_by_year CASCADE;
        CREATE OR REPLACE VIEW v_organizing_by_year AS
        SELECT 
            event_year as year,
            COUNT(*) as total_events,
            SUM(CASE WHEN event_type = 'election' THEN 1 ELSE 0 END) as elections,
            SUM(CASE WHEN event_type = 'voluntary_recognition' THEN 1 ELSE 0 END) as vr_cases,
            SUM(COALESCE(num_employees, 0)) as total_employees,
            COUNT(CASE WHEN union_won = 'true' THEN 1 END) as union_wins,
            ROUND(100.0 * COUNT(CASE WHEN union_won = 'true' THEN 1 END) / NULLIF(COUNT(*), 0), 1) as win_rate,
            COUNT(DISTINCT state) as states_active
        FROM v_all_organizing_events
        WHERE event_year IS NOT NULL
        GROUP BY event_year
        ORDER BY event_year
    """,
    
    'v_organizing_by_state': """
        DROP VIEW IF EXISTS v_organizing_by_state CASCADE;
        CREATE OR REPLACE VIEW v_organizing_by_state AS
        SELECT 
            state,
            COUNT(*) as total_events,
            SUM(CASE WHEN event_type = 'election' THEN 1 ELSE 0 END) as elections,
            SUM(CASE WHEN event_type = 'voluntary_recognition' THEN 1 ELSE 0 END) as vr_cases,
            SUM(COALESCE(num_employees, 0)) as total_employees,
            COUNT(CASE WHEN union_won = 'true' THEN 1 END) as union_wins,
            ROUND(100.0 * COUNT(CASE WHEN union_won = 'true' THEN 1 END) / NULLIF(COUNT(*), 0), 1) as win_rate
        FROM v_all_organizing_events
        WHERE state IS NOT NULL AND LENGTH(state) = 2
        GROUP BY state
        ORDER BY COUNT(*) DESC
    """,
    
    'v_vr_to_f7_pipeline': """
        DROP VIEW IF EXISTS v_vr_to_f7_pipeline CASCADE;
        CREATE OR REPLACE VIEW v_vr_to_f7_pipeline AS
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
            f7.latest_notice_date - vr.date_vr_request_received as days_vr_to_f7,
            CASE 
                WHEN f7.latest_notice_date > vr.date_vr_request_received THEN 'VR preceded F7'
                WHEN f7.latest_notice_date < vr.date_vr_request_received THEN 'F7 preceded VR'
                ELSE 'Same period'
            END as sequence_type
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
        WHERE vr.date_vr_request_received IS NOT NULL
          AND f7.latest_notice_date IS NOT NULL
    """,
    
    'v_vr_summary_stats': """
        DROP VIEW IF EXISTS v_vr_summary_stats CASCADE;
        CREATE OR REPLACE VIEW v_vr_summary_stats AS
        SELECT 
            COUNT(*) as total_vr_cases,
            COUNT(matched_employer_id) as employers_matched,
            COUNT(matched_union_fnum) as unions_matched,
            ROUND(100.0 * COUNT(matched_employer_id) / COUNT(*), 1) as employer_match_pct,
            ROUND(100.0 * COUNT(matched_union_fnum) / COUNT(*), 1) as union_match_pct,
            SUM(COALESCE(num_employees, 0)) as total_employees,
            AVG(num_employees)::int as avg_unit_size,
            COUNT(DISTINCT unit_state) as states_covered,
            COUNT(DISTINCT extracted_affiliation) as unique_affiliations,
            MIN(date_vr_request_received) as earliest_case,
            MAX(date_vr_request_received) as latest_case
        FROM nlrb_voluntary_recognition
    """
}

# Create each view
for view_name, sql in views_sql.items():
    try:
        cur.execute(sql)
        print(f"  Created {view_name}")
    except Exception as e:
        print(f"  ERROR creating {view_name}: {str(e)[:60]}")

# Verify views
print("\nVerifying cross-dataset views:")
for view_name in views_sql.keys():
    try:
        cur.execute(f"SELECT COUNT(*) FROM {view_name}")
        cnt = cur.fetchone()[0]
        print(f"  {view_name}: {cnt} rows")
    except Exception as e:
        print(f"  {view_name}: ERROR")

# Sample data from combined view
print("\nSample from v_organizing_by_year (recent):")
cur.execute("""
    SELECT year, total_events, elections, vr_cases, 
           total_employees, win_rate
    FROM v_organizing_by_year
    WHERE year >= 2020
    ORDER BY year
""")
print(f"  {'Year':<6} {'Total':<8} {'Elec':<8} {'VR':<6} {'Empl':<10} {'Win%':<6}")
print("  " + "-" * 50)
for row in cur.fetchall():
    print(f"  {row[0]:<6} {row[1]:<8} {row[2]:<8} {row[3]:<6} {row[4]:<10} {row[5]}")

cur.close()
conn.close()
print("\nCheckpoint 5B Complete!")
