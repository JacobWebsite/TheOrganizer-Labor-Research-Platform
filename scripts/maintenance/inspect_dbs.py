import sqlite3

# Inspect F-7 employers database
print("=" * 60)
print("F-7 EMPLOYERS DATABASE")
print("=" * 60)
conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\f7\employers_deduped.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"Tables: {tables}")

for table in tables:
    print(f"\n--- {table} ---")
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  Row count: {count:,}")

conn.close()

# Inspect crosswalk database
print("\n" + "=" * 60)
print("CROSSWALK DATABASE")
print("=" * 60)
conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\crosswalk\union_lm_f7_crosswalk.db')
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [t[0] for t in cursor.fetchall()]
print(f"Tables: {tables}")

for table in tables:
    print(f"\n--- {table} ---")
    cursor.execute(f"PRAGMA table_info({table})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"  {col[1]} ({col[2]})")
    cursor.execute(f"SELECT COUNT(*) FROM {table}")
    count = cursor.fetchone()[0]
    print(f"  Row count: {count:,}")

conn.close()
print("\nDone!")
