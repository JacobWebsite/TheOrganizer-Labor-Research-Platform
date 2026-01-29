"""
OSHA Historical Coverage Analysis
"""
import sqlite3

db_path = r"C:\Users\jakew\Downloads\osha_enforcement.db"
conn = sqlite3.connect(db_path)
cur = conn.cursor()

print("="*70)
print("OSHA DATA HISTORICAL COVERAGE")
print("="*70)

# Inspections by decade
cur.execute("""
    SELECT 
        CASE 
            WHEN substr(open_date,1,4) < '1980' THEN '1970s'
            WHEN substr(open_date,1,4) < '1990' THEN '1980s'
            WHEN substr(open_date,1,4) < '2000' THEN '1990s'
            WHEN substr(open_date,1,4) < '2010' THEN '2000s'
            WHEN substr(open_date,1,4) < '2020' THEN '2010s'
            ELSE '2020s'
        END as decade,
        COUNT(*) as inspections,
        COUNT(DISTINCT estab_name) as establishments
    FROM inspection
    WHERE open_date IS NOT NULL
    GROUP BY decade
    ORDER BY decade
""")
print("\nINSPECTIONS BY DECADE:")
print(f"{'Decade':<10} {'Inspections':>15} {'Establishments':>18}")
print("-"*45)
for row in cur.fetchall():
    print(f"{row[0]:<10} {row[1]:>15,} {row[2]:>18,}")

# Violations by decade
cur.execute("""
    SELECT 
        CASE 
            WHEN substr(issuance_date,1,4) < '1980' THEN '1970s'
            WHEN substr(issuance_date,1,4) < '1990' THEN '1980s'
            WHEN substr(issuance_date,1,4) < '2000' THEN '1990s'
            WHEN substr(issuance_date,1,4) < '2010' THEN '2000s'
            WHEN substr(issuance_date,1,4) < '2020' THEN '2010s'
            ELSE '2020s'
        END as decade,
        COUNT(*) as violations,
        SUM(current_penalty) as total_penalties
    FROM violation
    WHERE issuance_date IS NOT NULL AND issuance_date != 'issu'
    GROUP BY decade
    ORDER BY decade
""")
print("\nVIOLATIONS BY DECADE:")
print(f"{'Decade':<10} {'Violations':>15} {'Total Penalties':>20}")
print("-"*48)
for row in cur.fetchall():
    penalties = f"${row[2]:,.0f}" if row[2] else "$0"
    print(f"{row[0]:<10} {row[1]:>15,} {penalties:>20}")

# Recent years detail
cur.execute("""
    SELECT 
        substr(open_date,1,4) as year,
        COUNT(*) as inspections,
        COUNT(DISTINCT estab_name) as establishments
    FROM inspection
    WHERE open_date >= '2015-01-01'
    GROUP BY year
    ORDER BY year
""")
print("\nRECENT YEARS DETAIL (2015+):")
print(f"{'Year':<6} {'Inspections':>12} {'Establishments':>15}")
print("-"*35)
for row in cur.fetchall():
    print(f"{row[0]:<6} {row[1]:>12,} {row[2]:>15,}")

# Accidents by decade
cur.execute("""
    SELECT 
        CASE 
            WHEN substr(event_date,1,4) < '1990' THEN 'Pre-1990'
            WHEN substr(event_date,1,4) < '2000' THEN '1990s'
            WHEN substr(event_date,1,4) < '2010' THEN '2000s'
            WHEN substr(event_date,1,4) < '2020' THEN '2010s'
            ELSE '2020s'
        END as decade,
        COUNT(*) as accidents,
        SUM(CASE WHEN fatality = 'X' THEN 1 ELSE 0 END) as fatalities
    FROM accident
    WHERE event_date IS NOT NULL
    GROUP BY decade
    ORDER BY decade
""")
print("\nACCIDENTS/FATALITIES BY DECADE:")
print(f"{'Decade':<10} {'Accidents':>12} {'Fatalities':>12}")
print("-"*36)
for row in cur.fetchall():
    print(f"{row[0]:<10} {row[1]:>12,} {row[2]:>12,}")

conn.close()
