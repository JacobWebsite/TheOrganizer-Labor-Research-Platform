import os
"""
VR Integration Views - Checkpoint 5C
Final verification and comprehensive summary
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("VR INTEGRATION - CHECKPOINT 5 COMPLETE")
print("=" * 70)

# List all VR-related views
print("\n--- All VR-Related Views ---")
cur.execute("""
    SELECT table_name 
    FROM information_schema.views 
    WHERE table_schema = 'public' 
      AND (table_name LIKE 'v_vr_%' OR table_name LIKE 'v_organizing%' OR table_name LIKE 'v_all_%')
    ORDER BY table_name
""")
for row in cur.fetchall():
    view_name = row['table_name']
    try:
        cur.execute(f"SELECT COUNT(*) as cnt FROM {view_name}")
        cnt = cur.fetchone()['cnt']
        print(f"  {view_name}: {cnt:,} rows")
    except:
        print(f"  {view_name}: ERROR")

# Summary stats
print("\n--- VR Integration Summary ---")
cur.execute("SELECT * FROM v_vr_summary_stats")
stats = cur.fetchone()
print(f"  Total VR cases:        {stats['total_vr_cases']:,}")
print(f"  Employers matched:     {stats['employers_matched']:,} ({stats['employer_match_pct']}%)")
print(f"  Unions matched:        {stats['unions_matched']:,} ({stats['union_match_pct']}%)")
print(f"  Total employees:       {stats['total_employees']:,}")
print(f"  Avg unit size:         {stats['avg_unit_size']}")
print(f"  States covered:        {stats['states_covered']}")
print(f"  Affiliations:          {stats['unique_affiliations']}")
print(f"  Date range:            {stats['earliest_case']} to {stats['latest_case']}")

# Combined organizing summary
print("\n--- Combined Organizing Activity (2020-2025) ---")
cur.execute("""
    SELECT 
        SUM(total_events) as total,
        SUM(elections) as elections,
        SUM(vr_cases) as vr,
        SUM(total_employees) as employees
    FROM v_organizing_by_year 
    WHERE year >= 2020 AND year <= 2025
""")
combined = cur.fetchone()
print(f"  Total events:          {combined['total']:,}")
print(f"  NLRB Elections:        {combined['elections']:,}")
print(f"  Voluntary Recognitions:{combined['vr']:,}")
print(f"  Employees affected:    {combined['employees']:,}")

# Top states for combined activity
print("\n--- Top 10 States (Combined Activity) ---")
cur.execute("""
    SELECT state, total_events, elections, vr_cases, total_employees
    FROM v_organizing_by_state
    WHERE state IS NOT NULL
    ORDER BY total_events DESC
    LIMIT 10
""")
print(f"  {'State':<6} {'Total':<8} {'Elec':<8} {'VR':<6} {'Employees':<12}")
print("  " + "-" * 44)
for row in cur.fetchall():
    print(f"  {row['state']:<6} {row['total_events']:<8} {row['elections']:<8} {row['vr_cases']:<6} {row['total_employees']:,}")

# Pipeline insights
print("\n--- VR to F7 Pipeline Insights ---")
cur.execute("""
    SELECT sequence_type, COUNT(*) as cnt
    FROM v_vr_to_f7_pipeline
    GROUP BY sequence_type
""")
for row in cur.fetchall():
    print(f"  {row['sequence_type']}: {row['cnt']} cases")

cur.execute("""
    SELECT 
        AVG(days_vr_to_f7) as avg_days,
        MIN(days_vr_to_f7) as min_days,
        MAX(days_vr_to_f7) as max_days
    FROM v_vr_to_f7_pipeline
    WHERE sequence_type = 'VR preceded F7'
""")
pipeline = cur.fetchone()
print(f"\n  For VR-then-F7 cases:")
print(f"    Average time to F7 filing: {int(pipeline['avg_days'])} days (~{int(pipeline['avg_days'])/365:.1f} years)")
print(f"    Range: {pipeline['min_days']} to {pipeline['max_days']} days")

# New employers identified
print("\n--- New Employers (Not in F7) ---")
cur.execute("""
    SELECT COUNT(*) as cnt, SUM(COALESCE(num_employees, 0)) as emp
    FROM v_vr_new_employers
""")
new_emp = cur.fetchone()
print(f"  Count: {new_emp['cnt']:,}")
print(f"  Total employees: {new_emp['emp']:,}")

# Top new employers
print("\n  Top 5 by employee count:")
cur.execute("""
    SELECT employer_name, city, state, union_affiliation, num_employees
    FROM v_vr_new_employers
    WHERE num_employees IS NOT NULL
    ORDER BY num_employees DESC
    LIMIT 5
""")
for row in cur.fetchall():
    loc = f"{row['city']}, {row['state']}" if row['city'] else row['state'] or 'Unknown'
    print(f"    {row['employer_name'][:35]:35} | {loc:20} | {row['union_affiliation']:12} | {row['num_employees']} emp")

cur.close()
conn.close()

print("\n" + "=" * 70)
print("CHECKPOINT 5 COMPLETE - ALL VIEWS CREATED")
print("=" * 70)
print("\nViews available for API/UI integration:")
print("  - v_vr_cases_full         : Complete VR data with linkages")
print("  - v_vr_map_data           : VR data with coordinates for mapping")
print("  - v_vr_new_employers      : Employers with VR not yet in F7")
print("  - v_vr_yearly_summary     : Year-over-year VR trends")
print("  - v_vr_state_summary      : State-level VR analysis")
print("  - v_vr_affiliation_summary: Union affiliation breakdown")
print("  - v_all_organizing_events : Combined Elections + VR")
print("  - v_organizing_by_year    : Combined activity by year")
print("  - v_organizing_by_state   : Combined activity by state")
print("  - v_vr_to_f7_pipeline     : VR to F7 timing analysis")
print("  - v_vr_summary_stats      : Overall VR statistics")
print("\nNext: Checkpoint 6 - API Endpoint Integration")
