import os
import psycopg2
conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

print("=" * 90)
print("DEDUPLICATED OLMS MEMBERSHIP BY AFFILIATION")
print("=" * 90)

# Check the deduplication view
cur.execute("""
    SELECT * FROM v_dedup_summary_by_affiliation
    ORDER BY 2 DESC
    LIMIT 20
""")
cols = [desc[0] for desc in cur.description]
print(f"Columns: {cols}\n")

for r in cur.fetchall():
    print(r)

print("\n" + "=" * 90)
print("DEDUPLICATED BY LEVEL (National/Intermediate/Local)")
print("=" * 90)
cur.execute("SELECT * FROM v_dedup_summary_by_level")
for r in cur.fetchall():
    print(r)

print("\n" + "=" * 90)
print("DEDUPLICATION COMPARISON (Raw vs Deduplicated)")
print("=" * 90)
cur.execute("SELECT * FROM v_deduplication_comparison LIMIT 20")
cols = [desc[0] for desc in cur.description]
print(f"Columns: {cols}\n")
for r in cur.fetchall():
    print(r)

print("\n" + "=" * 90)
print("NHQ RECONCILED MEMBERSHIP")  
print("=" * 90)
cur.execute("SELECT * FROM nhq_reconciled_membership ORDER BY reconciled_members DESC LIMIT 20")
cols = [desc[0] for desc in cur.description]
print(f"Columns: {cols}\n")
for r in cur.fetchall():
    print(r)

conn.close()
