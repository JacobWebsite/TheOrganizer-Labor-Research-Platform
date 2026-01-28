"""
Quick test of API endpoints
"""
import psycopg2
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
cur = conn.cursor()

print("=" * 70)
print("TESTING API QUERIES")
print("=" * 70)

# Test affiliations query
print("\n--- Affiliations (top 10) ---")
cur.execute("""
    SELECT 
        aff_abbr,
        COUNT(*) as local_count,
        SUM(members) as total_members,
        COUNT(*) FILTER (WHERE has_f7_employers) as locals_with_employers
    FROM unions_master
    WHERE aff_abbr IS NOT NULL AND aff_abbr != ''
    GROUP BY aff_abbr
    HAVING COUNT(*) >= 5
    ORDER BY SUM(members) DESC NULLS LAST
    LIMIT 10
""")
for row in cur.fetchall():
    print(f"  {row['aff_abbr']:<10} {row['local_count']:>6} locals  {row['total_members'] or 0:>12,} members")

# Test union search with NLRB
print("\n--- SEIU locals with NLRB data ---")
cur.execute("""
    SELECT 
        um.f_num,
        um.union_name,
        um.members,
        COALESCE(nlrb.case_count, 0) as nlrb_cases
    FROM unions_master um
    LEFT JOIN (
        SELECT 
            x.olms_f_num::text as f_num,
            COUNT(DISTINCT c.case_number) as case_count
        FROM nlrb_union_xref x
        JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
        JOIN nlrb_cases c ON p.case_number = c.case_number
        WHERE x.olms_f_num IS NOT NULL
        GROUP BY x.olms_f_num
    ) nlrb ON um.f_num = nlrb.f_num
    WHERE um.aff_abbr = 'SEIU'
    ORDER BY um.members DESC NULLS LAST
    LIMIT 5
""")
for row in cur.fetchall():
    print(f"  {row['f_num']:<10} {row['union_name'][:40]:<42} {row['members'] or 0:>10,} members  {row['nlrb_cases']:>6} cases")

# Test union detail
print("\n--- Union detail: SEIU f_num=137 ---")
cur.execute("""
    SELECT 
        COUNT(DISTINCT c.case_number) as total_cases,
        COUNT(DISTINCT e.election_id) as total_elections,
        COUNT(DISTINCT CASE WHEN c.case_type = 'CA' THEN c.case_number END) as employer_ulp,
        COUNT(DISTINCT CASE WHEN c.case_type = 'CB' THEN c.case_number END) as union_ulp
    FROM nlrb_union_xref x
    JOIN nlrb_participants p ON x.nlrb_union_name = p.participant_name AND p.subtype = 'Union'
    JOIN nlrb_cases c ON p.case_number = c.case_number
    LEFT JOIN nlrb_elections e ON c.case_number = e.case_number
    WHERE x.olms_f_num = 137
""")
row = cur.fetchone()
print(f"  Total cases: {row['total_cases']}, Elections: {row['total_elections']}")
print(f"  Employer ULP (CA): {row['employer_ulp']}, Union ULP (CB): {row['union_ulp']}")

# Test employers
print("\n--- Employers for SEIU 137 ---")
cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped WHERE f_num = '137'
""")
print(f"  Total F-7 employers: {cur.fetchone()['cnt']}")

conn.close()
print("\n" + "=" * 70)
print("API queries working!")
print("=" * 70)
