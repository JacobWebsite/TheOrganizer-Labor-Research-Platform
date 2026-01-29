import sqlite3

conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

print("Counting 2012+ records...")

# Count inspections from 2012+
cursor.execute("""
    SELECT COUNT(*) 
    FROM inspection 
    WHERE open_date >= '2012-01-01'
""")
insp_count = cursor.fetchone()[0]
print(f"Inspections 2012+: {insp_count:,}")

# Count unique establishments from 2012+
cursor.execute("""
    SELECT COUNT(DISTINCT estab_name || '|' || COALESCE(site_address,'') || '|' || COALESCE(site_city,'') || '|' || COALESCE(site_state,''))
    FROM inspection 
    WHERE open_date >= '2012-01-01'
""")
est_count = cursor.fetchone()[0]
print(f"Unique establishments 2012+: {est_count:,}")

# Count violations from 2012+
cursor.execute("""
    SELECT COUNT(*) 
    FROM violation v
    JOIN inspection i ON v.activity_nr = i.activity_nr
    WHERE i.open_date >= '2012-01-01'
""")
viol_count = cursor.fetchone()[0]
print(f"Violations 2012+: {viol_count:,}")

# Count accidents from 2012+
cursor.execute("""
    SELECT COUNT(*) 
    FROM accident 
    WHERE event_date >= '2012-01-01'
""")
acc_count = cursor.fetchone()[0]
print(f"Accidents 2012+: {acc_count:,}")

# Breakdown by year
print("\nInspections by year:")
cursor.execute("""
    SELECT substr(open_date, 1, 4) as year, COUNT(*) as cnt
    FROM inspection 
    WHERE open_date >= '2012-01-01'
    GROUP BY substr(open_date, 1, 4)
    ORDER BY year
""")
for row in cursor.fetchall():
    print(f"  {row[0]}: {row[1]:,}")

conn.close()
