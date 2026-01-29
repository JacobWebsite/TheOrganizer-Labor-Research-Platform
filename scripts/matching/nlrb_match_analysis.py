import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost', 
    dbname='olms_multiyear', 
    user='postgres', 
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("NLRB PARTICIPANT MATCHING ANALYSIS")
print("=" * 60)

# Check unique union names in NLRB
cur.execute('''
    SELECT COUNT(DISTINCT LOWER(participant_name)) as unique_union_names
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
''')
result = cur.fetchone()
print(f"\nUnique union petitioner names in NLRB: {result['unique_union_names']:,}")

# Check how many can be matched via crosswalk - exact match
cur.execute('''
    SELECT COUNT(*) as matchable
    FROM nlrb_participants p
    INNER JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND c.pred_fnum IS NOT NULL
    AND c.pred_fnum_multiple = false
''')
result = cur.fetchone()
print(f"Matchable via exact crosswalk (single match): {result['matchable']:,}")

# Check how many unique names match
cur.execute('''
    SELECT COUNT(DISTINCT LOWER(p.participant_name)) as unique_matching
    FROM nlrb_participants p
    INNER JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND c.pred_fnum IS NOT NULL
''')
result = cur.fetchone()
print(f"Unique union names that match crosswalk: {result['unique_matching']:,}")

# Sample some union names to understand the data
cur.execute('''
    SELECT participant_name, COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' AND participant_subtype = 'Union'
    GROUP BY participant_name
    ORDER BY cnt DESC
    LIMIT 20
''')
print('\nTop 20 union petitioner names:')
for r in cur.fetchall():
    name = r['participant_name'][:55] if r['participant_name'] else 'NULL'
    print(f"  {name:55} : {r['cnt']:5}")

# Check crosswalk coverage
print("\n" + "=" * 60)
print("CROSSWALK COVERAGE CHECK")
print("=" * 60)

cur.execute('''
    SELECT 
        p.participant_name,
        c.union_name as crosswalk_name,
        c.pred_fnum,
        c.pred_aff,
        c.pred_union_score
    FROM nlrb_participants p
    LEFT JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    LIMIT 20
''')
print('\nSample matches (first 20 union petitioners):')
matched = 0
for r in cur.fetchall():
    name = r['participant_name'][:40] if r['participant_name'] else 'NULL'
    if r['crosswalk_name']:
        matched += 1
        print(f"  MATCH: {name:40} -> F#{r['pred_fnum']} ({r['pred_aff']})")
    else:
        print(f"  NO MATCH: {name:40}")

print(f"\nIn this sample: {matched}/20 matched")

conn.close()
print("\nAnalysis complete!")
