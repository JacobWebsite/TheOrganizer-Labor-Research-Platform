import os
from db_config import get_connection
"""Test VR API queries"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('Testing VR API queries...')
print()

# Test 1: Basic search
print('1. Basic VR search (limit 3):')
cur.execute("""
    SELECT vr.vr_case_number, vr.employer_name_normalized, vr.extracted_affiliation, vr.num_employees
    FROM nlrb_voluntary_recognition vr
    ORDER BY vr.date_vr_request_received DESC
    LIMIT 3
""")
for r in cur.fetchall():
    emp = r['employer_name_normalized'][:30] if r['employer_name_normalized'] else 'N/A'
    print(f"   {r['vr_case_number']}: {emp} | {r['extracted_affiliation']} | {r['num_employees']} emp")

print()

# Test 2: Filter by state
print('2. VR cases in California (top 3):')
cur.execute("""
    SELECT vr.vr_case_number, vr.employer_name_normalized, vr.extracted_affiliation
    FROM nlrb_voluntary_recognition vr
    WHERE vr.unit_state = 'CA'
    ORDER BY vr.num_employees DESC NULLS LAST
    LIMIT 3
""")
for r in cur.fetchall():
    emp = r['employer_name_normalized'][:40] if r['employer_name_normalized'] else 'N/A'
    print(f"   {r['vr_case_number']}: {emp}")

print()

# Test 3: Summary stats
print('3. Summary stats:')
cur.execute('SELECT * FROM v_vr_summary_stats')
stats = cur.fetchone()
print(f"   Total cases: {stats['total_vr_cases']}")
print(f"   Employers matched: {stats['employers_matched']} ({stats['employer_match_pct']}%)")
print(f"   Unions matched: {stats['unions_matched']} ({stats['union_match_pct']}%)")

print()

# Test 4: By year
print('4. By year (recent):')
cur.execute('SELECT * FROM v_vr_yearly_summary WHERE year >= 2020 ORDER BY year')
for r in cur.fetchall():
    print(f"   {r['year']}: {r['total_cases']} cases, {r['total_employees']} employees")

print()

# Test 5: New employers
print('5. New employers (top 5 by size):')
cur.execute("""
    SELECT employer_name, city, state, union_affiliation, num_employees
    FROM v_vr_new_employers
    WHERE num_employees IS NOT NULL
    ORDER BY num_employees DESC
    LIMIT 5
""")
for r in cur.fetchall():
    emp = r['employer_name'][:35] if r['employer_name'] else 'N/A'
    loc = f"{r['city']}, {r['state']}" if r['city'] else r['state'] or 'N/A'
    print(f"   {emp:35} | {loc:20} | {r['num_employees']} emp")

print()

# Test 6: Pipeline
print('6. VR to F7 Pipeline:')
cur.execute("""
    SELECT sequence_type, COUNT(*) as cnt, AVG(days_vr_to_f7)::int as avg_days
    FROM v_vr_to_f7_pipeline
    GROUP BY sequence_type
""")
for r in cur.fetchall():
    print(f"   {r['sequence_type']}: {r['cnt']} cases, avg {r['avg_days']} days")

print()
print('All queries successful!')
conn.close()
