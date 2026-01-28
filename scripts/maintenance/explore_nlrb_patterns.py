import sqlite3

nlrb = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\nlrb\nlrb.db')
cursor = nlrb.cursor()

print("=== UNIQUE UNION NAMES IN NLRB (Top 30 by frequency) ===")
cursor.execute("""
    SELECT participant, COUNT(*) as cnt 
    FROM participant 
    WHERE subtype='Union' AND participant IS NOT NULL
    GROUP BY participant 
    ORDER BY cnt DESC 
    LIMIT 30
""")
for row in cursor.fetchall():
    name = row[0][:80] if row[0] else 'NULL'
    print(f"{row[1]:>6,}  {name}")

print("\n=== UNIQUE EMPLOYER NAMES IN NLRB (Top 30 by frequency) ===")
cursor.execute("""
    SELECT participant, COUNT(*) as cnt 
    FROM participant 
    WHERE subtype='Employer' AND participant IS NOT NULL
    GROUP BY participant 
    ORDER BY cnt DESC 
    LIMIT 30
""")
for row in cursor.fetchall():
    name = row[0][:80] if row[0] else 'NULL'
    print(f"{row[1]:>6,}  {name}")

print("\n=== TOTAL UNIQUE UNIONS ===")
cursor.execute("SELECT COUNT(DISTINCT participant) FROM participant WHERE subtype='Union' AND participant IS NOT NULL")
print(f"Unique union names: {cursor.fetchone()[0]:,}")

print("\n=== TOTAL UNIQUE EMPLOYERS ===")
cursor.execute("SELECT COUNT(DISTINCT participant) FROM participant WHERE subtype='Employer' AND participant IS NOT NULL")
print(f"Unique employer names: {cursor.fetchone()[0]:,}")

nlrb.close()
