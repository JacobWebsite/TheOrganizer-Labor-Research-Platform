import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
tables = cursor.fetchall()
print('=== Tables in OSHA database ===')
for t in tables:
    cursor.execute(f"SELECT COUNT(*) FROM [{t[0]}]")
    count = cursor.fetchone()[0]
    print(f'  {t[0]:40} {count:>12,} rows')

conn.close()
