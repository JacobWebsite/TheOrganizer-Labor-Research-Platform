import sqlite3
conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

# Check fatality column values
cursor.execute("SELECT fatality, COUNT(*) FROM accident WHERE event_date >= '2012-01-01' GROUP BY fatality")
print("Fatality column values (2012+):")
for r in cursor.fetchall():
    print(f"  {repr(r[0])}: {r[1]:,}")

# Check how accidents link to inspections
print("\nChecking accident-inspection linkage via related_activity...")
cursor.execute("""
    SELECT COUNT(*) 
    FROM accident a
    JOIN related_activity ra ON a.summary_nr = ra.rel_act_nr AND ra.rel_type = 'A'
    WHERE a.event_date >= '2012-01-01'
""")
print(f"Accidents linked via related_activity: {cursor.fetchone()[0]:,}")

# Sample accident with inspection
cursor.execute("""
    SELECT a.summary_nr, a.event_date, a.fatality, a.event_desc, i.estab_name, i.site_city, i.site_state
    FROM accident a
    JOIN related_activity ra ON a.summary_nr = ra.rel_act_nr AND ra.rel_type = 'A'
    JOIN inspection i ON ra.activity_nr = i.activity_nr
    WHERE a.event_date >= '2012-01-01'
    LIMIT 3
""")
print("\nSample accidents with inspection data:")
for r in cursor.fetchall():
    print(f"  {r}")

conn.close()
