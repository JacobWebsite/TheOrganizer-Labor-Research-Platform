import os
"""Final verification after all Phase 2 fixes"""
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 70)
print("FINAL VERIFICATION")
print("=" * 70)

# 1. Zero empty employer_name_aggressive (unfixable ones are flagged)
cur.execute("""
    SELECT COUNT(*) as cnt FROM f7_employers_deduped
    WHERE (employer_name_aggressive IS NULL OR TRIM(employer_name_aggressive) = '')
    AND data_quality_flag IS NULL
""")
r = cur.fetchone()
print(f"1. Unflagged empty employer_name_aggressive: {r['cnt']} (should be 0)")

# 2. Zero unionized records with score_priority
cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = TRUE AND score_priority IS NOT NULL
""")
r = cur.fetchone()
print(f"2. Unionized with score_priority: {r['cnt']} (should be 0)")

# 3. Mergent names are lowercase
cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE company_name_normalized != LOWER(company_name_normalized)
    AND company_name_normalized IS NOT NULL
""")
r = cur.fetchone()
print(f"3. Mergent non-lowercase names: {r['cnt']} (should be 0)")

# 4. Sector views working
cur.execute("SELECT COUNT(*) as cnt FROM v_museums_organizing_targets")
r = cur.fetchone()
print(f"4. Museum targets view records: {r['cnt']} (should be 218)")

cur.execute("SELECT COUNT(*) as cnt FROM v_education_organizing_targets")
r = cur.fetchone()
print(f"   Education targets view: {r['cnt']}")

# 5. Score consistency
cur.execute("""
    SELECT COUNT(*) as cnt FROM mergent_employers
    WHERE has_union = FALSE AND organizing_score IS NOT NULL
      AND organizing_score != COALESCE(score_geographic, 0) +
                              COALESCE(score_size, 0) +
                              COALESCE(score_industry_density, 0) +
                              COALESCE(score_nlrb_momentum, 0) +
                              COALESCE(score_osha_violations, 0) +
                              COALESCE(score_govt_contracts, 0) +
                              COALESCE(sibling_union_bonus, 0) +
                              COALESCE(score_labor_violations, 0)
""")
r = cur.fetchone()
print(f"5. Score formula mismatches: {r['cnt']} (should be 0)")

# 6. data_quality_flag distribution
cur.execute("""
    SELECT data_quality_flag, COUNT(*) as cnt
    FROM f7_employers_deduped
    WHERE data_quality_flag IS NOT NULL
    GROUP BY data_quality_flag
    ORDER BY COUNT(*) DESC
""")
rows = cur.fetchall()
print(f"\n6. data_quality_flag distribution:")
for r in rows:
    print(f"   {r['data_quality_flag']}: {r['cnt']}")

# 7. Total counts
cur.execute("SELECT COUNT(*) as cnt FROM f7_employers_deduped")
f7_total = cur.fetchone()['cnt']
cur.execute("SELECT COUNT(*) as cnt FROM mergent_employers")
m_total = cur.fetchone()['cnt']
cur.execute("SELECT COUNT(*) as cnt FROM mergent_employers WHERE has_union = TRUE")
m_union = cur.fetchone()['cnt']
cur.execute("SELECT COUNT(*) as cnt FROM mergent_employers WHERE has_union = FALSE")
m_targets = cur.fetchone()['cnt']
print(f"\n7. Record counts:")
print(f"   f7_employers_deduped: {f7_total:,}")
print(f"   mergent_employers: {m_total:,} (unionized: {m_union}, targets: {m_targets})")

print("\n" + "=" * 70)
print("ALL VERIFICATIONS COMPLETE")
print("=" * 70)

cur.close()
conn.close()
