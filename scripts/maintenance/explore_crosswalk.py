import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\crosswalk\union_lm_f7_crosswalk.db')
cursor = conn.cursor()

print("=== CROSSWALK DATABASE TABLES ===")
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
for row in tables:
    print(row[0])

print("\n=== TABLE SCHEMAS AND COUNTS ===")
for table in [t[0] for t in tables if not t[0].startswith('sqlite')]:
    print(f"\n--- {table} ---")
    cursor.execute(f"PRAGMA table_info({table})")
    for col in cursor.fetchall():
        print(f"  {col[1]}: {col[2]}")
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    print(f"  Count: {cursor.fetchone()[0]:,}")

print("\n=== SAMPLE unions_master ===")
cursor.execute("SELECT * FROM unions_master LIMIT 5")
cols = [desc[0] for desc in cursor.description]
print(cols)
for row in cursor.fetchall():
    print(row)

print("\n=== SAMPLE f7_employers ===")
cursor.execute("SELECT * FROM f7_employers LIMIT 5")
cols = [desc[0] for desc in cursor.description]
print(cols)
for row in cursor.fetchall():
    print(row)

conn.close()
