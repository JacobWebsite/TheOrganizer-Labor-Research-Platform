"""
NLRB Participant Matching - Phase 2: Analyze Unmatched Records
==============================================================
Identifies patterns in unmatched union petitioner names to develop
additional matching strategies.
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import re
from collections import Counter

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("ANALYZING UNMATCHED NLRB UNION PETITIONERS")
print("=" * 70)

# Get unmatched union petitioner names
cur.execute("""
    SELECT participant_name, COUNT(*) as cnt
    FROM nlrb_participants
    WHERE participant_type = 'Petitioner' 
    AND participant_subtype = 'Union'
    AND matched_olms_fnum IS NULL
    GROUP BY participant_name
    ORDER BY cnt DESC
""")
unmatched = cur.fetchall()
print(f"\nUnique unmatched union names: {len(unmatched):,}")
print(f"Total unmatched records: {sum(r['cnt'] for r in unmatched):,}")

# Top unmatched names
print("\n" + "-" * 70)
print("TOP 30 UNMATCHED UNION NAMES (by frequency)")
print("-" * 70)
for i, r in enumerate(unmatched[:30], 1):
    name = r['participant_name'][:60] if r['participant_name'] else 'NULL'
    print(f"{i:2}. {name:60} : {r['cnt']:4}")

# Analyze patterns in unmatched names
print("\n" + "-" * 70)
print("PATTERN ANALYSIS")
print("-" * 70)

affiliations = Counter()
patterns = {
    'local_number': re.compile(r'local\s*(\d+)', re.I),
    'afl_cio': re.compile(r'afl[\-\s]*cio', re.I),
    'seiu': re.compile(r'seiu|service\s+employees', re.I),
    'teamsters': re.compile(r'teamster|ibt', re.I),
    'ufcw': re.compile(r'ufcw|food\s+(?:and\s+)?commercial', re.I),
    'cwa': re.compile(r'\bcwa\b|communication.*workers', re.I),
    'unite_here': re.compile(r'unite\s*here', re.I),
    'iuoe': re.compile(r'operating\s+engineers|i\.?u\.?o\.?e', re.I),
    'usw': re.compile(r'\busw\b|steelworkers|steel.*workers', re.I),
    'uaw': re.compile(r'\buaw\b|auto.*workers', re.I),
    'ibew': re.compile(r'\bibew\b|electrical.*workers', re.I),
    'iam': re.compile(r'\biam\b|machinists|aerospace', re.I),
    'workers_united': re.compile(r'workers\s+united', re.I),
    'afscme': re.compile(r'afscme|state.*county.*municipal', re.I),
    'aft': re.compile(r'\baft\b|teachers.*federation', re.I),
    'nea': re.compile(r'\bnea\b|education.*association', re.I),
}

pattern_counts = Counter()
for r in unmatched:
    name = r['participant_name'] or ''
    for pattern_name, pattern in patterns.items():
        if pattern.search(name):
            pattern_counts[pattern_name] += r['cnt']

print("\nAffiliation patterns detected in unmatched names:")
for pattern, count in pattern_counts.most_common():
    print(f"  {pattern:20}: {count:5} records")

# Check for multi-match crosswalk entries
print("\n" + "-" * 70)
print("MULTI-MATCH CROSSWALK ANALYSIS")
print("-" * 70)

cur.execute("""
    SELECT COUNT(*) as matchable_multi
    FROM nlrb_participants p
    INNER JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND p.matched_olms_fnum IS NULL
    AND c.pred_fnum_multiple = true
""")
multi = cur.fetchone()
print(f"Records matching multi-fnum crosswalk entries: {multi['matchable_multi']:,}")

# Sample multi-match cases
cur.execute("""
    SELECT p.participant_name, c.pred_fnum, c.pred_aff, c.pred_union_score
    FROM nlrb_participants p
    INNER JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND p.matched_olms_fnum IS NULL
    AND c.pred_fnum_multiple = true
    LIMIT 10
""")
print("\nSample multi-match cases:")
for r in cur.fetchall():
    name = r['participant_name'][:45] if r['participant_name'] else 'NULL'
    print(f"  {name:45} -> {r['pred_fnum']} ({r['pred_aff']})")

# Check for names with no crosswalk match at all
print("\n" + "-" * 70)
print("NO CROSSWALK MATCH ANALYSIS")
print("-" * 70)

cur.execute("""
    SELECT p.participant_name, COUNT(*) as cnt
    FROM nlrb_participants p
    LEFT JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND p.matched_olms_fnum IS NULL
    AND c.union_name IS NULL
    GROUP BY p.participant_name
    ORDER BY cnt DESC
    LIMIT 30
""")
no_match = cur.fetchall()
total_no_match = sum(r['cnt'] for r in no_match)

print(f"\nNames with NO crosswalk match (top 30 of {len(no_match):,}):")
for r in no_match[:30]:
    name = r['participant_name'][:55] if r['participant_name'] else 'NULL'
    print(f"  {name:55}: {r['cnt']:4}")

print("\n" + "-" * 70)
print("AFFILIATION-BASED MATCHING POTENTIAL")
print("-" * 70)

# Check if we can match based on affiliation patterns + local numbers
cur.execute("""
    SELECT c.pred_aff, COUNT(*) as cnt
    FROM nlrb_participants p
    INNER JOIN union_names_crosswalk c ON LOWER(p.participant_name) = LOWER(c.union_name)
    WHERE p.participant_type = 'Petitioner' 
    AND p.participant_subtype = 'Union'
    AND p.matched_olms_fnum IS NULL
    AND c.pred_aff IS NOT NULL
    GROUP BY c.pred_aff
    ORDER BY cnt DESC
    LIMIT 15
""")
print("\nTop affiliations in unmatched-but-crosswalk-found:")
for r in cur.fetchall():
    print(f"  {r['pred_aff']:15}: {r['cnt']:5} records")

conn.close()
print("\nAnalysis complete!")
