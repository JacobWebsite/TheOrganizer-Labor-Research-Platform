import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\nlrb\nlrb.db')
cursor = conn.cursor()

print("=== SAMPLE UNION PARTICIPANTS ===")
cursor.execute("SELECT case_number, participant, type, subtype, city, state FROM participant WHERE subtype='Union' LIMIT 10")
for row in cursor.fetchall():
    print(row)

print("\n=== SAMPLE EMPLOYER PARTICIPANTS ===")
cursor.execute("SELECT case_number, participant, type, subtype, city, state FROM participant WHERE subtype='Employer' LIMIT 10")
for row in cursor.fetchall():
    print(row)

print("\n=== SAMPLE FILINGS ===")
cursor.execute("SELECT case_number, name, case_type, city, state, date_filed, status, certified_representative FROM filing LIMIT 10")
for row in cursor.fetchall():
    print(row)

print("\n=== CASE TYPES ===")
cursor.execute("SELECT case_type, COUNT(*) as cnt FROM filing GROUP BY case_type ORDER BY cnt DESC")
for row in cursor.fetchall():
    print(row)

print("\n=== DATE RANGES ===")
cursor.execute("SELECT MIN(date_filed), MAX(date_filed) FROM filing")
print(cursor.fetchone())

conn.close()
