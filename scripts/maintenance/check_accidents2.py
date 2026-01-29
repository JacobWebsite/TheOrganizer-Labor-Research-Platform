import sqlite3
conn = sqlite3.connect(r'C:\Users\jakew\Downloads\osha_enforcement.db')
cursor = conn.cursor()

# Check rel_insp_nr in accident_injury
print("Checking accident_injury.rel_insp_nr linkage...")
cursor.execute("""
    SELECT COUNT(DISTINCT ai.summary_nr)
    FROM accident_injury ai
    JOIN accident a ON ai.summary_nr = a.summary_nr
    JOIN inspection i ON ai.rel_insp_nr = i.activity_nr
    WHERE a.event_date >= '2012-01-01'
""")
print(f"Accidents with inspection link via accident_injury.rel_insp_nr: {cursor.fetchone()[0]:,}")

# Sample with establishment data
cursor.execute("""
    SELECT a.summary_nr, a.event_date, a.fatality, i.estab_name, i.site_city, i.site_state, 
           COUNT(*) as injury_count
    FROM accident a
    JOIN accident_injury ai ON a.summary_nr = ai.summary_nr
    JOIN inspection i ON ai.rel_insp_nr = i.activity_nr
    WHERE a.event_date >= '2012-01-01'
    GROUP BY a.summary_nr, a.event_date, a.fatality, i.estab_name, i.site_city, i.site_state
    LIMIT 5
""")
print("\nSample accidents via accident_injury link:")
for r in cursor.fetchall():
    print(f"  {r}")

# Count total with any inspection link
cursor.execute("""
    SELECT COUNT(DISTINCT a.summary_nr)
    FROM accident a
    JOIN accident_injury ai ON a.summary_nr = ai.summary_nr
    WHERE a.event_date >= '2012-01-01' AND ai.rel_insp_nr IS NOT NULL
""")
print(f"\nTotal accidents with rel_insp_nr in accident_injury: {cursor.fetchone()[0]:,}")

conn.close()
