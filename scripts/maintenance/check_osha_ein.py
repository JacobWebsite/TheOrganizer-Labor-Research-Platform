import sqlite3
conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

# Check for EIN-like columns in inspection table
cursor.execute("PRAGMA table_info(inspection)")
columns = cursor.fetchall()
print("=== inspection table columns ===")
for col in columns:
    print(f"  {col[1]}")

# Check for any table with 'ein' in name
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE '%ein%'")
tables = cursor.fetchall()
print(f"\nTables with 'ein' in name: {tables}")

# Check optional_info table (often has additional employer data)
cursor.execute("PRAGMA table_info(optional_info)")
columns = cursor.fetchall()
print("\n=== optional_info table columns ===")
for col in columns:
    print(f"  {col[1]}")

# Sample optional_info
cursor.execute("SELECT * FROM optional_info LIMIT 3")
print("\nSample optional_info:")
for row in cursor.fetchall():
    print(f"  {row}")

conn.close()
