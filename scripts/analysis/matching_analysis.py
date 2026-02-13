import os
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('ENTITY MATCHING ANALYSIS - CURRENT STATE')
print('='*70)

# 1. F-7 EMPLOYER -> UNION MATCHING
print('\n### 1. F-7 EMPLOYER -> UNION MATCHING ###')
cur.execute('SELECT COUNT(*) as total FROM f7_employers_deduped')
total_f7 = cur.fetchone()['total']

cur.execute('SELECT COUNT(*) as matched FROM f7_employers_deduped WHERE latest_union_fnum IS NOT NULL')
matched_f7 = cur.fetchone()['matched']

print(f'Total F-7 employers: {total_f7:,}')
print(f'Matched to union (latest_union_fnum): {matched_f7:,} ({100*matched_f7/total_f7:.1f}%)')
print(f'Unmatched: {total_f7 - matched_f7:,}')

# Workers in unmatched
cur.execute('''
    SELECT SUM(latest_unit_size) as workers
    FROM f7_employers_deduped 
    WHERE latest_union_fnum IS NULL AND latest_unit_size > 0
''')
unmatched_workers = cur.fetchone()['workers'] or 0
print(f'Unmatched employers represent: {unmatched_workers:,.0f} workers')

# Top unmatched by workers
cur.execute('''
    SELECT latest_union_name, COUNT(*) as cnt, SUM(latest_unit_size) as workers
    FROM f7_employers_deduped 
    WHERE latest_union_fnum IS NULL AND latest_union_name IS NOT NULL
    GROUP BY latest_union_name
    ORDER BY workers DESC NULLS LAST
    LIMIT 15
''')
print('\nTop unmatched union names by workers:')
for row in cur.fetchall():
    print(f"  {row['latest_union_name'][:55]}: {row['cnt']:,} emp, {row['workers'] or 0:,.0f} workers")

# 2. NLRB ELECTION -> UNION MATCHING
print('\n### 2. NLRB ELECTION -> UNION MATCHING ###')
cur.execute('SELECT COUNT(*) as total FROM nlrb_tallies')
total_nlrb = cur.fetchone()['total']

cur.execute('SELECT COUNT(*) as matched FROM nlrb_tallies WHERE matched_olms_fnum IS NOT NULL')
matched_nlrb = cur.fetchone()['matched']

print(f'Total NLRB tallies: {total_nlrb:,}')
print(f'Matched to union: {matched_nlrb:,} ({100*matched_nlrb/total_nlrb:.1f}%)')
print(f'Unmatched: {total_nlrb - matched_nlrb:,}')

# Top unmatched NLRB unions
cur.execute('''
    SELECT labor_org_name, COUNT(*) as cnt
    FROM nlrb_tallies 
    WHERE matched_olms_fnum IS NULL AND labor_org_name IS NOT NULL
    GROUP BY labor_org_name
    ORDER BY cnt DESC
    LIMIT 15
''')
print('\nTop unmatched NLRB union names:')
for row in cur.fetchall():
    name = row['labor_org_name'][:60] if row['labor_org_name'] else 'NULL'
    print(f"  {name}: {row['cnt']:,}")

# 3. VOLUNTARY RECOGNITION MATCHING
print('\n### 3. VOLUNTARY RECOGNITION MATCHING ###')
cur.execute('SELECT COUNT(*) as total FROM nlrb_voluntary_recognition')
total_vr = cur.fetchone()['total']

cur.execute('SELECT COUNT(*) as matched FROM nlrb_voluntary_recognition WHERE matched_union_fnum IS NOT NULL')
matched_vr_union = cur.fetchone()['matched']

cur.execute('SELECT COUNT(*) as matched FROM nlrb_voluntary_recognition WHERE matched_employer_id IS NOT NULL')
matched_vr_emp = cur.fetchone()['matched']

print(f'Total VR cases: {total_vr:,}')
print(f'Matched to union: {matched_vr_union:,} ({100*matched_vr_union/total_vr:.1f}%)')
print(f'Matched to F-7 employer: {matched_vr_emp:,} ({100*matched_vr_emp/total_vr:.1f}%)')

# 4. LOCAL -> NATIONAL HIERARCHY
print('\n### 4. LOCAL -> NATIONAL UNION HIERARCHY ###')

# Check designation breakdown from lm_data
cur.execute('''
    SELECT desig_name, COUNT(DISTINCT f_num) as unions, SUM(members) as total_members
    FROM lm_data 
    WHERE yr_covered >= 2024
    GROUP BY desig_name
    ORDER BY unions DESC
''')
print('Union designations (2024 data):')
for row in cur.fetchall():
    members = row['total_members'] or 0
    print(f"  {row['desig_name'] or 'NULL'}: {row['unions']:,} unions, {members:,.0f} members")

# Locals without clear affiliation
cur.execute('''
    SELECT COUNT(DISTINCT f_num) as cnt
    FROM lm_data
    WHERE desig_name = 'Local' AND (aff_abbr IS NULL OR aff_abbr = '')
    AND yr_covered >= 2024
''')
orphan_locals = cur.fetchone()['cnt']
print(f'\nLocals without affiliation (2024): {orphan_locals:,}')

# Check unions_master affiliation coverage
cur.execute('''
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN aff_abbr IS NOT NULL AND aff_abbr != '' THEN 1 END) as has_aff
    FROM unions_master
''')
row = cur.fetchone()
print(f'\nunions_master: {row["total"]:,} total, {row["has_aff"]:,} with affiliation ({100*row["has_aff"]/row["total"]:.1f}%)')

# 5. COVERAGE CALCULATION
print('\n### 5. MEMBERSHIP COVERAGE ESTIMATE ###')

# Get reconciled F7 workers
cur.execute('SELECT SUM(reconciled_workers) as total FROM v_f7_private_sector_reconciled')
f7_reconciled = cur.fetchone()['total'] or 0

# Get VR workers
cur.execute('SELECT SUM(num_employees) as total FROM nlrb_voluntary_recognition')
vr_total = cur.fetchone()['total'] or 0

cur.execute('SELECT SUM(num_employees) as total FROM nlrb_voluntary_recognition WHERE matched_union_fnum IS NOT NULL')
vr_matched = cur.fetchone()['total'] or 0

print(f'F-7 reconciled private sector: {f7_reconciled:,.0f}')
print(f'VR total workers: {vr_total:,.0f}')
print(f'VR with matched unions: {vr_matched:,.0f}')
print(f'\nBLS Benchmarks:')
print(f'  Private sector: 7,300,000')
print(f'  Total (all sectors): 14,300,000')
print(f'\nCurrent coverage:')
print(f'  F-7 vs BLS private: {100*f7_reconciled/7300000:.1f}%')
print(f'  F-7 + VR vs BLS private: {100*(f7_reconciled + vr_total)/7300000:.1f}%')

# 6. IMPROVEMENT OPPORTUNITY SUMMARY
print('\n' + '='*70)
print('IMPROVEMENT OPPORTUNITIES SUMMARY')
print('='*70)

print(f'''
CURRENT STATE:
- F-7 employer->union match rate: {100*matched_f7/total_f7:.1f}% ({total_f7 - matched_f7:,} unmatched)
- NLRB tally->union match rate: {100*matched_nlrb/total_nlrb:.1f}% ({total_nlrb - matched_nlrb:,} unmatched)  
- VR->union match rate: {100*matched_vr_union/total_vr:.1f}% ({total_vr - matched_vr_union:,} unmatched)
- VR->employer match rate: {100*matched_vr_emp/total_vr:.1f}% ({total_vr - matched_vr_emp:,} unmatched)

UNMATCHED WORKERS:
- F-7 unmatched employers: {unmatched_workers:,.0f} workers
- This represents significant potential coverage gain

TOP IMPROVEMENT AREAS:
1. F-7 regional councils (Carpenters, SEIU, etc.) - need council->national mapping
2. NLRB elections - 54% unmatched, biggest absolute gap
3. SAG-AFTRA variations in F-7 names
4. Building trades multi-employer associations
''')

conn.close()
print('\nDone!')
