import os
from db_config import get_connection
"""Export county union density estimates to CSV"""
import psycopg2
import csv
from pathlib import Path

conn = get_connection()
cur = conn.cursor()

output_path = Path(r"C:\Users\jakew\Downloads\labor-data-project\output\county_union_density_estimates.csv")
output_path.parent.mkdir(exist_ok=True)

print("Exporting county union density estimates to CSV...")

cur.execute("""
    SELECT
        e.fips,
        e.state,
        e.county_name,
        ROUND(e.estimated_total_density, 2) as estimated_total_density,
        ROUND(e.estimated_private_density, 2) as estimated_private_density,
        ROUND(e.estimated_public_density, 2) as estimated_public_density,
        ROUND(e.estimated_federal_density, 2) as estimated_federal_density,
        ROUND(e.estimated_state_density, 2) as estimated_state_density,
        ROUND(e.estimated_local_density, 2) as estimated_local_density,
        ROUND(w.private_share * 100, 2) as private_workforce_pct,
        ROUND(w.federal_gov_share * 100, 2) as federal_workforce_pct,
        ROUND(w.state_gov_share * 100, 2) as state_workforce_pct,
        ROUND(w.local_gov_share * 100, 2) as local_workforce_pct,
        ROUND(w.public_share * 100, 2) as public_workforce_pct,
        ROUND(w.self_employed_share * 100, 2) as self_employed_pct,
        e.confidence_level,
        ROUND(e.state_multiplier, 3) as state_union_multiplier
    FROM county_union_density_estimates e
    JOIN county_workforce_shares w ON e.fips = w.fips
    ORDER BY e.state, e.county_name
""")

rows = cur.fetchall()
columns = [
    'fips', 'state', 'county_name',
    'estimated_total_density', 'estimated_private_density', 'estimated_public_density',
    'estimated_federal_density', 'estimated_state_density', 'estimated_local_density',
    'private_workforce_pct', 'federal_workforce_pct', 'state_workforce_pct',
    'local_workforce_pct', 'public_workforce_pct', 'self_employed_pct',
    'confidence_level', 'state_union_multiplier'
]

with open(output_path, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(columns)
    writer.writerows(rows)

print(f"Exported {len(rows)} counties to: {output_path}")

cur.close()
conn.close()
