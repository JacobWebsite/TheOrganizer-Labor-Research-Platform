import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor()

# Check nlrb_tallies for union matching
print("=" * 60)
print("NLRB TALLIES UNION MATCHING")
print("=" * 60)

cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'nlrb_tallies'
    AND (column_name LIKE '%match%' OR column_name LIKE '%olms%' OR column_name LIKE '%fnum%')
""")
print("Matching columns in nlrb_tallies:")
for r in cur.fetchall():
    print(f"  {r[0]}")

cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_olms_fnum) as matched
    FROM nlrb_tallies
""")
row = cur.fetchone()
print(f"\nTotal tallies: {row[0]:,}")
print(f"Union matched to OLMS: {row[1]:,} ({100*row[1]/row[0]:.1f}%)" if row[0] > 0 else "")

# Get sample F7 employers for fuzzy matching comparison
print("\n" + "=" * 60)
print("SAMPLE F7 EMPLOYERS (targets for matching)")
print("=" * 60)
cur.execute("""
    SELECT employer_name, city, state, latest_union_name
    FROM f7_employers_deduped
    WHERE employer_name IS NOT NULL
    ORDER BY RANDOM()
    LIMIT 15
""")
for row in cur.fetchall():
    print(f"  {row[0][:50]:50} | {row[1] or ''}, {row[2] or ''}")

# Count quality NLRB employers (not law firms, not empty)
print("\n" + "=" * 60)
print("NLRB EMPLOYER DATA QUALITY")
print("=" * 60)
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN participant_name IS NOT NULL 
                   AND LENGTH(TRIM(participant_name)) > 3
                   AND participant_name NOT LIKE '%Law%'
                   AND participant_name NOT LIKE '%P.C.%'
                   AND participant_name NOT LIKE '%LLP%'
                   AND participant_name NOT LIKE '%Esq%'
                   THEN 1 END) as valid_employers
    FROM nlrb_participants
    WHERE participant_type = 'Employer'
""")
row = cur.fetchone()
print(f"Total NLRB employers: {row[0]:,}")
print(f"Valid for matching (non-law firm, has name): {row[1]:,} ({100*row[1]/row[0]:.1f}%)")

conn.close()
