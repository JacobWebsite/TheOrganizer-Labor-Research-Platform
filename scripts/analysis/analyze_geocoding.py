import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\crosswalk\union_lm_f7_crosswalk.db')
cursor = conn.cursor()

print("=== GEOCODING STATUS SUMMARY ===")
cursor.execute("""
    SELECT geocode_status, COUNT(*) as cnt, 
           ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM f7_employers), 2) as pct
    FROM f7_employers 
    GROUP BY geocode_status
""")
for row in cursor.fetchall():
    print(f"{row[0] or 'NULL':>12}: {row[1]:>8,} ({row[2]}%)")

print("\n=== FAILED GEOCODES - SAMPLE ADDRESSES ===")
cursor.execute("""
    SELECT employer_name, street, city, state, zip
    FROM f7_employers 
    WHERE geocode_status = 'failed'
    LIMIT 20
""")
for row in cursor.fetchall():
    print(f"{row[0][:40]:<42} | {row[1] or 'NO STREET':<40} | {row[2]}, {row[3]} {row[4]}")

print("\n=== FAILED GEOCODES - ADDRESS PATTERNS ===")
cursor.execute("""
    SELECT 
        CASE 
            WHEN street IS NULL OR street = '' THEN 'No street address'
            WHEN street LIKE 'PO Box%' OR street LIKE 'P.O.%' OR street LIKE 'P O Box%' THEN 'PO Box only'
            WHEN street LIKE '%\n%' THEN 'Multi-line address'
            WHEN zip IS NULL OR zip = '' THEN 'Missing ZIP'
            WHEN LENGTH(street) < 10 THEN 'Short/incomplete street'
            ELSE 'Other'
        END as pattern,
        COUNT(*) as cnt
    FROM f7_employers 
    WHERE geocode_status = 'failed'
    GROUP BY pattern
    ORDER BY cnt DESC
""")
for row in cursor.fetchall():
    print(f"{row[0]:<30}: {row[1]:>6,}")

print("\n=== FAILED BY STATE (Top 10) ===")
cursor.execute("""
    SELECT state, COUNT(*) as failed,
           (SELECT COUNT(*) FROM f7_employers f2 WHERE f2.state = f7_employers.state) as total,
           ROUND(100.0 * COUNT(*) / (SELECT COUNT(*) FROM f7_employers f2 WHERE f2.state = f7_employers.state), 1) as fail_pct
    FROM f7_employers 
    WHERE geocode_status = 'failed'
    GROUP BY state
    ORDER BY failed DESC
    LIMIT 10
""")
print(f"{'State':<6} {'Failed':>8} {'Total':>8} {'Fail %':>8}")
for row in cursor.fetchall():
    print(f"{row[0]:<6} {row[1]:>8,} {row[2]:>8,} {row[3]:>7.1f}%")

conn.close()
