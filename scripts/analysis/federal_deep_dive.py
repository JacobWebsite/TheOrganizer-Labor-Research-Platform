import os
import psycopg2
from db_config import get_connection
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

print('='*70)
print('DEEP DIVE: TRUE FEDERAL EMPLOYERS IN PRIVATE SECTOR')
print('='*70)

# Check for actual federal agencies (not private companies with similar names)
print('\n### 1. Searching for TRUE Federal Agency Patterns in PRIVATE ###')

# These are definitively federal
definite_federal = [
    ('Department of Veterans Affairs', "f.employer_name ILIKE 'department of veterans affairs%'"),
    ('VA Medical Center', "f.employer_name ILIKE '%va medical center%'"),
    ('VA Healthcare', "f.employer_name ILIKE '%va healthcare%'"),
    ('USPS/Postal Service', "f.employer_name ILIKE 'united states postal%'"),
    ('Internal Revenue Service', "f.employer_name ILIKE '%internal revenue service%'"),
    ('Social Security Admin', "f.employer_name ILIKE '%social security admin%'"),
    ('DOD/Pentagon', "f.employer_name ILIKE '%department of defense%'"),
    ('Air Force Base', "f.employer_name ILIKE '%air force base%'"),
    ('Army Installation', "f.employer_name ILIKE '%army installation%' OR f.employer_name ILIKE '%fort %army%'"),
    ('Navy Base', "f.employer_name ILIKE '%naval%' OR f.employer_name ILIKE '%navy yard%'"),
    ('TSA', "f.employer_name ILIKE '%transportation security%'"),
    ('CBP/ICE', "f.employer_name ILIKE '%customs and border%' OR f.employer_name ILIKE '%border protection%'"),
]

total_misclass = 0
for name, condition in definite_federal:
    cur.execute(f"""
        SELECT COUNT(*) as cnt, SUM(f.latest_unit_size) as workers
        FROM f7_employers_deduped f
        LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
        WHERE u.sector_revised = 'PRIVATE'
        AND ({condition})
    """)
    result = cur.fetchone()
    if result['cnt'] > 0:
        print(f"  {name}: {result['cnt']} employers, {result['workers'] or 0:,} workers")
        total_misclass += result['workers'] or 0

print(f"\n  TOTAL TRUE FEDERAL in PRIVATE: {total_misclass:,}")

# 2. Check SEIU employers that might be federal (VA hospitals)
print('\n\n### 2. SEIU Employers with Federal-Sounding Names ###')
cur.execute("""
    SELECT f.employer_name, f.latest_unit_size, u.sector_revised
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr = 'SEIU'
    AND (f.employer_name ILIKE '%veteran%' 
         OR f.employer_name ILIKE '%va %'
         OR f.employer_name ILIKE '%federal%')
    ORDER BY f.latest_unit_size DESC NULLS LAST
    LIMIT 15
""")
print(f"{'Employer':<55} {'Workers':>10} {'Sector':>15}")
print('-'*85)
for row in cur.fetchall():
    print(f"{row['employer_name'][:55]:<55} {row['latest_unit_size'] or 0:>10,} {row['sector_revised']:>15}")

# 3. What unions represent federal workers per OPM? Check if they're in wrong sector
print('\n\n### 3. Federal Unions (per OPM) - Check All Sectors ###')
federal_unions = ['AFGE', 'NTEU', 'NFFE', 'NAGE', 'NALC', 'APWU', 'NPMHU']

for union in federal_unions:
    cur.execute("""
        SELECT u.sector_revised, COUNT(DISTINCT f.employer_id) as employers, SUM(f.latest_unit_size) as workers
        FROM f7_employers_deduped f
        JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
        WHERE u.aff_abbr = %s
        GROUP BY u.sector_revised
        ORDER BY workers DESC
    """, (union,))
    results = cur.fetchall()
    if results:
        print(f"\n{union}:")
        for row in results:
            print(f"  {row['sector_revised']}: {row['employers']} employers, {row['workers'] or 0:,} workers")

# 4. TVA - special case (federal agency but uses NLRA)
print('\n\n### 4. TVA (Tennessee Valley Authority) - Special Case ###')
cur.execute("""
    SELECT f.employer_name, f.latest_unit_size, u.aff_abbr, u.sector_revised
    FROM f7_employers_deduped f
    LEFT JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE f.employer_name ILIKE '%tennessee valley%'
       OR f.employer_name ILIKE '%tva%'
    ORDER BY f.latest_unit_size DESC NULLS LAST
""")
tva_total = 0
for row in cur.fetchall():
    print(f"  {row['employer_name'][:50]}: {row['latest_unit_size'] or 0:,} ({row['aff_abbr']}, {row['sector_revised']})")
    tva_total += row['latest_unit_size'] or 0
print(f"\nTVA Total: {tva_total:,}")
print("Note: TVA is unique - federal agency but uses NLRA, not FSLMRA")

# 5. Summary
print('\n\n' + '='*70)
print('SUMMARY: FEDERAL IN F-7')
print('='*70)

cur.execute("""
    SELECT u.sector_revised, SUM(f.latest_unit_size) as workers
    FROM f7_employers_deduped f
    JOIN unions_master u ON f.latest_union_fnum::text = u.f_num
    WHERE u.aff_abbr IN ('AFGE', 'NTEU', 'NFFE', 'NAGE', 'NALC', 'APWU', 'NPMHU')
    GROUP BY u.sector_revised
    ORDER BY workers DESC
""")
print('\nFederal Union Workers by Sector Classification:')
for row in cur.fetchall():
    print(f"  {row['sector_revised']}: {row['workers'] or 0:,}")

conn.close()
