"""
990 vs OLMS Cross-Validation
Use 990 dues revenue to validate deduplicated OLMS membership counts
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

print("=" * 90)
print("CROSS-VALIDATION: 990 IMPLIED MEMBERSHIP vs DEDUPLICATED OLMS")
print("=" * 90)

# Check what's in form_990_estimates table
print("\nCurrent form_990_estimates table contents:")
cur.execute("SELECT COUNT(*) FROM form_990_estimates")
count = cur.fetchone()[0]
print(f"  Total records: {count}")

if count > 0:
    cur.execute("""
        SELECT org_type, COUNT(*), SUM(estimated_members)
        FROM form_990_estimates
        GROUP BY org_type
        ORDER BY SUM(estimated_members) DESC
    """)
    print(f"\n  {'Org Type':<30} {'Count':>8} {'Est Members':>15}")
    print("  " + "-" * 55)
    for r in cur.fetchall():
        print(f"  {r[0]:<30} {r[1]:>8} {r[2]:>15,}")

# Check deduplicated OLMS totals from lm_data_deduped if it exists
print("\n" + "=" * 90)
print("DEDUPLICATED OLMS DATA (if available)")
print("=" * 90)

cur.execute("""
    SELECT EXISTS (
        SELECT FROM information_schema.tables 
        WHERE table_name = 'lm_data_deduped'
    )
""")
if cur.fetchone()[0]:
    cur.execute("""
        SELECT aff_abbr, COUNT(*), SUM(members)
        FROM lm_data_deduped
        GROUP BY aff_abbr
        ORDER BY SUM(members) DESC NULLS LAST
        LIMIT 15
    """)
    print(f"{'Affiliation':<15} {'Orgs':>8} {'Deduped Members':>18}")
    print("-" * 45)
    for r in cur.fetchall():
        print(f"{r[0] or 'Unknown':<15} {r[1]:>8} {r[2] or 0:>18,}")
else:
    print("lm_data_deduped table not found")
    
    # Check reconciled_union_totals
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'reconciled_union_totals'
        )
    """)
    if cur.fetchone()[0]:
        print("\nUsing reconciled_union_totals instead:")
        cur.execute("SELECT * FROM reconciled_union_totals ORDER BY reconciled_members DESC LIMIT 15")
        cols = [desc[0] for desc in cur.description]
        print(f"  Columns: {cols}")
        for r in cur.fetchall():
            print(f"  {r}")

# Check what tables exist related to deduplication
print("\n" + "=" * 90)
print("AVAILABLE TABLES FOR ANALYSIS")
print("=" * 90)
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_schema = 'public'
    AND (table_name LIKE '%dedup%' 
         OR table_name LIKE '%reconcil%'
         OR table_name LIKE '%990%'
         OR table_name LIKE '%union_total%')
    ORDER BY table_name
""")
for r in cur.fetchall():
    print(f"  {r[0]}")

conn.close()
