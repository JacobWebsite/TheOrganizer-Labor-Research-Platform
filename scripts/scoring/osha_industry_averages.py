"""
OSHA violation averages by NAICS code.
Serves as a proxy for BLS SOII injury rates.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# --- 1. OSHA violation rate by 2-digit NAICS ---
print("=" * 100)
print("1. OSHA VIOLATION RATE BY 2-DIGIT NAICS (min 50 establishments)")
print("=" * 100)

cur.execute("""
    SELECT LEFT(oe.naics_code, 2) as naics_2,
           COUNT(DISTINCT oe.establishment_id) as establishments,
           COUNT(vd.id) as total_violations,
           ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as avg_violations_per_estab,
           ROUND(SUM(vd.current_penalty)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as avg_penalty_per_estab
    FROM osha_establishments oe
    LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
    WHERE oe.naics_code IS NOT NULL AND LENGTH(oe.naics_code) >= 2
    GROUP BY LEFT(oe.naics_code, 2)
    HAVING COUNT(DISTINCT oe.establishment_id) >= 50
    ORDER BY avg_violations_per_estab DESC
""")

rows = cur.fetchall()
print(f"{'NAICS-2':<10} {'Estabs':>10} {'Violations':>12} {'Avg Viol/Est':>14} {'Avg Penalty/Est':>16}")
print("-" * 64)
for r in rows:
    print(f"{r[0]:<10} {r[1]:>10,} {r[2]:>12,} {float(r[3]):>14.2f} ${float(r[4]):>15,.2f}")
print(f"\nTotal rows: {len(rows)}")

# --- 2. OSHA violation rate by 4-digit NAICS ---
print("\n" + "=" * 100)
print("2. OSHA VIOLATION RATE BY 4-DIGIT NAICS (min 20 establishments, top 40 by avg violations)")
print("=" * 100)

cur.execute("""
    SELECT LEFT(oe.naics_code, 4) as naics_4,
           COUNT(DISTINCT oe.establishment_id) as establishments,
           COUNT(vd.id) as total_violations,
           ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as avg_violations_per_estab,
           ROUND(SUM(vd.current_penalty)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as avg_penalty_per_estab
    FROM osha_establishments oe
    LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
    WHERE oe.naics_code IS NOT NULL AND LENGTH(oe.naics_code) >= 4
    GROUP BY LEFT(oe.naics_code, 4)
    HAVING COUNT(DISTINCT oe.establishment_id) >= 20
    ORDER BY avg_violations_per_estab DESC
""")

rows4 = cur.fetchall()
print(f"{'NAICS-4':<10} {'Estabs':>10} {'Violations':>12} {'Avg Viol/Est':>14} {'Avg Penalty/Est':>16}")
print("-" * 64)
for r in rows4[:40]:
    print(f"{r[0]:<10} {r[1]:>10,} {r[2]:>12,} {float(r[3]):>14.2f} ${float(r[4]):>15,.2f}")
print(f"\nTotal NAICS-4 groups (>=20 estabs): {len(rows4)}")

# --- 3. Overall average baseline ---
print("\n" + "=" * 100)
print("3. OVERALL BASELINE AVERAGE")
print("=" * 100)

cur.execute("""
    SELECT COUNT(DISTINCT oe.establishment_id) as total_estabs,
           COUNT(vd.id) as total_violations,
           ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as overall_avg
    FROM osha_establishments oe
    LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
""")

baseline = cur.fetchone()
print(f"Total establishments:  {baseline[0]:>12,}")
print(f"Total violations:      {baseline[1]:>12,}")
print(f"Overall avg viol/est:  {float(baseline[2]):>12.2f}")

# --- Summary stats ---
print("\n" + "=" * 100)
print("SUMMARY: Top 5 most dangerous 2-digit NAICS")
print("=" * 100)

naics_labels = {
    "11": "Agriculture", "21": "Mining", "22": "Utilities", "23": "Construction",
    "31": "Manufacturing", "32": "Manufacturing", "33": "Manufacturing",
    "42": "Wholesale Trade", "44": "Retail Trade", "45": "Retail Trade",
    "48": "Transportation", "49": "Transportation", "51": "Information",
    "52": "Finance/Insurance", "53": "Real Estate", "54": "Professional Svc",
    "55": "Management", "56": "Admin/Waste", "61": "Education",
    "62": "Healthcare", "71": "Arts/Entertainment", "72": "Accommodation/Food",
    "81": "Other Services", "92": "Public Admin"
}

cur.execute("""
    SELECT LEFT(oe.naics_code, 2) as naics_2,
           COUNT(DISTINCT oe.establishment_id) as establishments,
           ROUND(COUNT(vd.id)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as avg_violations_per_estab,
           ROUND(SUM(vd.current_penalty)::numeric / NULLIF(COUNT(DISTINCT oe.establishment_id), 0), 2) as avg_penalty_per_estab
    FROM osha_establishments oe
    LEFT JOIN osha_violations_detail vd ON vd.establishment_id = oe.establishment_id
    WHERE oe.naics_code IS NOT NULL AND LENGTH(oe.naics_code) >= 2
    GROUP BY LEFT(oe.naics_code, 2)
    HAVING COUNT(DISTINCT oe.establishment_id) >= 50
    ORDER BY avg_violations_per_estab DESC
    LIMIT 5
""")

for r in cur.fetchall():
    label = naics_labels.get(r[0], "Unknown")
    print(f"  NAICS {r[0]} ({label}): {float(r[2]):.2f} violations/estab, ${float(r[3]):,.2f} avg penalty")

cur.close()
conn.close()
print("\nDone.")
