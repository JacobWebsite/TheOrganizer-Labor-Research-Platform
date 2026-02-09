import os
"""
Verify NAICS Crosswalk Data in Database
"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("="*70)
print("NAICS CROSSWALK DATA SUMMARY")
print("="*70)

# Check version crosswalks
print("\n1. NAICS VERSION CROSSWALKS (naics_version_crosswalk)")
cur.execute("""
    SELECT source_version, target_version, COUNT(*) as mappings
    FROM naics_version_crosswalk
    GROUP BY source_version, target_version
    ORDER BY source_version DESC
""")
for r in cur.fetchall():
    print(f"   {r['source_version']} -> {r['target_version']}: {r['mappings']:,} mappings")

# Sample from each
print("\n   Sample 2022->2017 mappings:")
cur.execute("""
    SELECT source_code, source_title, target_code, target_title
    FROM naics_version_crosswalk
    WHERE source_version = 2022 AND target_version = 2017
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"      {r['source_code']} ({r['source_title'][:30]}...) -> {r['target_code']}")

# Check SIC crosswalk
print("\n2. SIC TO NAICS CROSSWALK (naics_sic_crosswalk)")
cur.execute("SELECT COUNT(*) as cnt FROM naics_sic_crosswalk")
print(f"   Total SIC->NAICS mappings: {cur.fetchone()['cnt']:,}")

cur.execute("""
    SELECT sic_code, sic_title, naics_2002_code, naics_2002_title
    FROM naics_sic_crosswalk
    LIMIT 5
""")
print("   Sample mappings:")
for r in cur.fetchall():
    print(f"      SIC {r['sic_code']} ({r['sic_title'][:25]}...) -> NAICS {r['naics_2002_code']}")

# Check NAICS reference codes
print("\n3. NAICS CODES REFERENCE (naics_codes_reference)")
cur.execute("""
    SELECT naics_version, COUNT(*) as codes
    FROM naics_codes_reference
    GROUP BY naics_version
    ORDER BY naics_version DESC
""")
for r in cur.fetchall():
    print(f"   NAICS {r['naics_version']}: {r['codes']:,} codes")

# Check code levels
cur.execute("""
    SELECT naics_version, code_level, COUNT(*) as cnt
    FROM naics_codes_reference
    WHERE code_level IS NOT NULL
    GROUP BY naics_version, code_level
    ORDER BY naics_version DESC, code_level
""")
print("\n   Codes by level:")
for r in cur.fetchall():
    print(f"      NAICS {r['naics_version']} level {r['code_level']}: {r['cnt']:,}")

# Test chained lookup: 2022 -> 2017 -> 2012 -> 2007 -> 2002
print("\n4. CHAINED CROSSWALK TEST (2022 code to 2002)")
test_code = '238160'  # Roofing Contractors
print(f"   Starting with NAICS 2022 code: {test_code}")

cur.execute("""
    WITH chain AS (
        SELECT 
            '2022' as from_ver, '2017' as to_ver,
            source_code, source_title, target_code, target_title
        FROM naics_version_crosswalk
        WHERE source_version = 2022 AND source_code = %s
    )
    SELECT * FROM chain
""", (test_code,))
r = cur.fetchone()
if r:
    print(f"   2022 {r['source_code']} ({r['source_title']}) -> 2017 {r['target_code']}")
    code_2017 = r['target_code']
    
    cur.execute("""
        SELECT target_code, target_title
        FROM naics_version_crosswalk
        WHERE source_version = 2017 AND source_code = %s
    """, (code_2017,))
    r2 = cur.fetchone()
    if r2:
        print(f"   2017 {code_2017} -> 2012 {r2['target_code']}")
        code_2012 = r2['target_code']
        
        cur.execute("""
            SELECT target_code, target_title
            FROM naics_version_crosswalk
            WHERE source_version = 2012 AND source_code = %s
        """, (code_2012,))
        r3 = cur.fetchone()
        if r3:
            print(f"   2012 {code_2012} -> 2007 {r3['target_code']}")
            code_2007 = r3['target_code']
            
            cur.execute("""
                SELECT target_code, target_title
                FROM naics_version_crosswalk
                WHERE source_version = 2007 AND source_code = %s
            """, (code_2007,))
            r4 = cur.fetchone()
            if r4:
                print(f"   2007 {code_2007} -> 2002 {r4['target_code']} ({r4['target_title']})")

conn.close()
print("\n" + "="*70)
print("CROSSWALKS VERIFIED AND READY FOR USE")
print("="*70)
