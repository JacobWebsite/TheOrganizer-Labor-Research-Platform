import os
import psycopg2
from db_config import get_connection
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('=== CURRENT EMPLOYER-UNION LINKAGE STATUS ===\n')

# 1. F-7 Employer to Union matching
print('1. F-7 EMPLOYERS -> UNIONS')
cur.execute('''
    SELECT 
        COUNT(*) as total_employers,
        COUNT(latest_union_fnum) as has_union_fnum,
        COUNT(DISTINCT latest_union_fnum) as unique_unions_linked
    FROM f7_employers_deduped
''')
r = cur.fetchone()
total_emp = r["total_employers"]
has_fnum = r["has_union_fnum"]
print(f'   Total F-7 employers: {total_emp:,}')
print(f'   With union file number: {has_fnum:,} ({100*has_fnum/total_emp:.1f}%)')
print(f'   Unique unions linked: {r["unique_unions_linked"]:,}')

# Check if those file numbers actually exist in unions_master
cur.execute('''
    SELECT COUNT(DISTINCT e.latest_union_fnum) as matched
    FROM f7_employers_deduped e
    JOIN unions_master u ON e.latest_union_fnum::text = u.f_num::text
    WHERE e.latest_union_fnum IS NOT NULL
''')
r = cur.fetchone()
print(f'   File numbers found in unions_master: {r["matched"]:,}')

# 2. OLMS Union hierarchy
print('\n2. OLMS UNION HIERARCHY (locals -> nationals)')
cur.execute('''
    SELECT desig_name, COUNT(*) as cnt
    FROM lm_data
    WHERE yr_covered >= 2024
    GROUP BY desig_name
    ORDER BY cnt DESC
''')
print('   Designation breakdown (2024+):')
for r in cur.fetchall():
    print(f'      {r["desig_name"]}: {r["cnt"]:,}')

# Check affiliation linkage
cur.execute('''
    SELECT 
        COUNT(*) as total,
        COUNT(aff_abbr) as has_affiliation,
        COUNT(DISTINCT aff_abbr) as unique_affiliations
    FROM unions_master
''')
r = cur.fetchone()
print(f'   Unions with affiliation: {r["has_affiliation"]:,} of {r["total"]:,} ({100*r["has_affiliation"]/r["total"]:.1f}%)')
print(f'   Unique affiliations: {r["unique_affiliations"]:,}')

# 3. NLRB election matching
print('\n3. NLRB ELECTIONS -> UNIONS')
cur.execute('SELECT COUNT(*) as total FROM nlrb_tallies')
total_tallies = cur.fetchone()['total']

cur.execute('SELECT COUNT(*) as matched FROM nlrb_tallies WHERE matched_olms_fnum IS NOT NULL')
matched_tallies = cur.fetchone()['matched']
print(f'   Total election tallies: {total_tallies:,}')
print(f'   Matched to OLMS unions: {matched_tallies:,} ({100*matched_tallies/total_tallies:.1f}%)')
print(f'   UNMATCHED: {total_tallies - matched_tallies:,}')

# 4. VR matching
print('\n4. VOLUNTARY RECOGNITION -> UNIONS/EMPLOYERS')
cur.execute('''
    SELECT 
        COUNT(*) as total,
        COUNT(matched_union_fnum) as union_matched,
        COUNT(matched_employer_id) as employer_matched
    FROM nlrb_voluntary_recognition
''')
r = cur.fetchone()
print(f'   Total VR cases: {r["total"]:,}')
print(f'   Union matched: {r["union_matched"]:,} ({100*r["union_matched"]/r["total"]:.1f}%)')
print(f'   Employer matched: {r["employer_matched"]:,} ({100*r["employer_matched"]/r["total"]:.1f}%)')

# 5. Workers coverage by linkage status
print('\n5. WORKERS BY LINKAGE STATUS (F-7)')
cur.execute('''
    SELECT 
        CASE WHEN latest_union_fnum IS NOT NULL THEN 'Has Union Link' ELSE 'No Union Link' END as status,
        COUNT(*) as employers,
        SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE latest_unit_size > 0
    GROUP BY CASE WHEN latest_union_fnum IS NOT NULL THEN 'Has Union Link' ELSE 'No Union Link' END
''')
for r in cur.fetchall():
    print(f'   {r["status"]}: {r["employers"]:,} employers, {r["workers"]:,.0f} workers')

# 6. Check what data is available for unmatched NLRB
print('\n6. UNMATCHED NLRB ELECTION SAMPLE (union names)')
cur.execute('''
    SELECT labor_union, COUNT(*) as cnt
    FROM nlrb_tallies
    WHERE matched_olms_fnum IS NULL
    GROUP BY labor_union
    ORDER BY cnt DESC
    LIMIT 15
''')
print('   Top unmatched union names:')
for r in cur.fetchall():
    name = r["labor_union"][:60] if r["labor_union"] else "NULL"
    print(f'      "{name}": {r["cnt"]}')

# 7. Check councils/intermediates
print('\n7. COUNCILS AND INTERMEDIATE BODIES')
cur.execute('''
    SELECT desig_name, aff_abbr, COUNT(*) as cnt
    FROM lm_data
    WHERE desig_name IN ('Intermediate Body', 'Subordinate')
    AND yr_covered >= 2024
    GROUP BY desig_name, aff_abbr
    ORDER BY cnt DESC
    LIMIT 20
''')
print('   Top intermediate/subordinate bodies by affiliation:')
for r in cur.fetchall():
    print(f'      {r["desig_name"]} - {r["aff_abbr"]}: {r["cnt"]:,}')

# 8. Employers without union match - what do we have?
print('\n8. F-7 EMPLOYERS WITHOUT UNION FILE NUMBER')
cur.execute('''
    SELECT COUNT(*) as cnt, 
           COUNT(latest_union_name) as has_name,
           SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL
''')
r = cur.fetchone()
print(f'   Count: {r["cnt"]:,}')
print(f'   With union name text: {r["has_name"]:,}')
print(f'   Workers: {r["workers"]:,.0f}' if r["workers"] else '   Workers: 0')

# Sample of unmatched employer union names
cur.execute('''
    SELECT latest_union_name, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NULL AND latest_union_name IS NOT NULL
    GROUP BY latest_union_name
    ORDER BY cnt DESC
    LIMIT 15
''')
print('   Top unmatched union name patterns:')
for r in cur.fetchall():
    name = r["latest_union_name"][:50] if r["latest_union_name"] else "NULL"
    print(f'      "{name}": {r["cnt"]}')

# 9. Summary - how much of BLS can we map?
print('\n=== SUMMARY: BLS MAPPING POTENTIAL ===')
print('BLS Total Union Members: 14.3M')
print('BLS Private Sector: 7.3M')
print('')

# Get linked workers
cur.execute('''
    SELECT SUM(latest_unit_size) as workers
    FROM f7_employers_deduped
    WHERE latest_union_fnum IS NOT NULL AND latest_unit_size > 0
''')
linked = cur.fetchone()['workers']
print(f'F-7 workers with union link: {linked:,.0f}')

# Get linked + reconciled
cur.execute('SELECT SUM(reconciled_workers) as total FROM v_f7_private_sector_reconciled')
reconciled = cur.fetchone()['total']
print(f'F-7 reconciled private sector: {reconciled:,.0f}')
print(f'Coverage of BLS private: {100*reconciled/7300000:.1f}%')

conn.close()
print('\nDone!')
