import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

print("=" * 60)
print("F7 EMPLOYER MATCHING STATUS")
print("=" * 60)

# F7 employers with union file numbers
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(CASE WHEN latest_union_fnum IS NOT NULL THEN 1 END) as has_union_fnum,
        COUNT(DISTINCT latest_union_fnum) as unique_unions
    FROM f7_employers_deduped
""")
row = cur.fetchone()
print(f"\nTotal F7 employers: {row[0]:,}")
print(f"With union file number: {row[1]:,} ({100*row[1]/row[0]:.1f}%)")
print(f"Unique unions linked: {row[2]:,}")

# Check NLRB matching columns on other tables
print("\n" + "=" * 60)
print("NLRB EMPLOYER MATCHING STATUS")
print("=" * 60)

cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'nlrb_participants'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print(f"\nnlrb_participants columns: {cols}")

# Check if there's employer matching on NLRB side
if 'matched_employer_id' in cols:
    cur.execute("""
        SELECT 
            COUNT(*) as total,
            COUNT(matched_employer_id) as matched
        FROM nlrb_participants
        WHERE participant_group = 'Employer'
    """)
    row = cur.fetchone()
    print(f"\nNLRB employer participants: {row[0]:,}")
    print(f"Matched to F7: {row[1]:,} ({100*row[1]/row[0]:.1f}%)" if row[0] > 0 else "")

# Check union matching
cur.execute("""
    SELECT column_name 
    FROM information_schema.columns 
    WHERE table_name = 'nlrb_tallies'
    ORDER BY ordinal_position
""")
cols = [r[0] for r in cur.fetchall()]
print(f"\nnlrb_tallies columns: {cols[:15]}...")  # First 15

conn.close()
