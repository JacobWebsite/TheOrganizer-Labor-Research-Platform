import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\labor-data-project\data\crosswalk\union_lm_f7_crosswalk.db')
cursor = conn.cursor()

print("=== 'OTHER' FAILED GEOCODES - SAMPLE (look complete but failed) ===")
cursor.execute("""
    SELECT employer_name, street, city, state, zip
    FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND street IS NOT NULL 
      AND street != ''
      AND street NOT LIKE 'PO Box%' 
      AND street NOT LIKE 'P.O.%'
      AND street NOT LIKE 'P O Box%'
      AND street NOT LIKE '%\n%'
      AND LENGTH(street) >= 10
      AND zip IS NOT NULL 
      AND zip != ''
    LIMIT 40
""")
for row in cursor.fetchall():
    street = row[1][:45] if row[1] else ''
    print(f"{street:<47} | {row[2]}, {row[3]} {row[4]}")

print("\n=== CHECKING FOR COMMON ISSUES IN 'OTHER' ===")

# Check for special characters
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE '%#%' OR street LIKE '%Suite%' OR street LIKE '%Ste%' OR street LIKE '%Unit%')
""")
print(f"Contains Suite/Unit/# : {cursor.fetchone()[0]:,}")

# Check for highway/route addresses
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE '%Highway%' OR street LIKE '%Route%' OR street LIKE '%Hwy%' OR street LIKE '%Rt %')
""")
print(f"Highway/Route address : {cursor.fetchone()[0]:,}")

# Check for rural/county roads
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE '%County%' OR street LIKE '%CR %' OR street LIKE '%RR %' OR street LIKE '%Rural%')
""")
print(f"County/Rural road     : {cursor.fetchone()[0]:,}")

# Check for intersections
cursor.execute("""
    SELECT COUNT(*) FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE '% & %' OR street LIKE '% and %' OR street LIKE '%corner%')
""")
print(f"Intersection address  : {cursor.fetchone()[0]:,}")

print("\n=== PO BOX ADDRESSES - CAN WE USE CITY/STATE/ZIP? ===")
cursor.execute("""
    SELECT city, state, zip, COUNT(*) as cnt
    FROM f7_employers 
    WHERE geocode_status = 'failed'
      AND (street LIKE 'PO Box%' OR street LIKE 'P.O.%' OR street LIKE 'P O Box%')
      AND city IS NOT NULL AND state IS NOT NULL AND zip IS NOT NULL
    GROUP BY city, state, zip
    ORDER BY cnt DESC
    LIMIT 10
""")
print("Top cities with PO Box failures:")
for row in cursor.fetchall():
    print(f"  {row[0]}, {row[1]} {row[2]}: {row[3]} employers")

print("\n=== NULL GEOCODE STATUS - NEVER ATTEMPTED? ===")
cursor.execute("""
    SELECT employer_name, street, city, state, zip
    FROM f7_employers 
    WHERE geocode_status IS NULL
    LIMIT 10
""")
for row in cursor.fetchall():
    street = row[1][:40] if row[1] else 'NO STREET'
    print(f"{street:<42} | {row[2]}, {row[3]} {row[4]}")

conn.close()
