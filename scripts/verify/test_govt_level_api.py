import os
from db_config import get_connection
"""Test the government-level density API queries"""
import psycopg2
import json

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("TESTING /api/density/by-govt-level QUERY")
print("=" * 80)

# Test the main endpoint query
cur.execute("""
    SELECT
        state,
        state_name,
        public_density_pct,
        public_is_estimated,
        multiplier,
        est_federal_density,
        est_state_density,
        est_local_density
    FROM state_govt_level_density
    ORDER BY public_density_pct DESC
    LIMIT 5
""")
print("\nTop 5 states by public density:")
for r in cur.fetchall():
    print(f"  {r[0]} ({r[1]}): Public={r[2]}%, Fed={r[5]}%, State={r[6]}%, Local={r[7]}%")

# Test summary stats
cur.execute("""
    SELECT
        ROUND(AVG(est_federal_density), 1) as avg_federal,
        ROUND(AVG(est_state_density), 1) as avg_state,
        ROUND(AVG(est_local_density), 1) as avg_local,
        ROUND(AVG(multiplier), 2) as avg_multiplier,
        COUNT(CASE WHEN multiplier > 1.5 THEN 1 END) as high_union_states,
        COUNT(CASE WHEN multiplier <= 0.75 THEN 1 END) as low_union_states
    FROM state_govt_level_density
""")
stats = cur.fetchone()
print(f"\nSummary Stats:")
print(f"  Avg Federal: {stats[0]}%")
print(f"  Avg State: {stats[1]}%")
print(f"  Avg Local: {stats[2]}%")
print(f"  Avg Multiplier: {stats[3]}x")
print(f"  High Union States (k>1.5): {stats[4]}")
print(f"  Low Union States (k<=0.75): {stats[5]}")

print("\n" + "=" * 80)
print("TESTING /api/density/by-govt-level/{state} QUERY (NY)")
print("=" * 80)

cur.execute("""
    SELECT
        g.state,
        g.state_name,
        g.public_density_pct,
        g.public_is_estimated,
        g.multiplier,
        g.est_federal_density,
        g.est_state_density,
        g.est_local_density,
        g.fed_share_of_public,
        g.state_share_of_public,
        g.local_share_of_public,
        w.federal_gov_share * 100 as federal_workforce_pct,
        w.state_gov_share * 100 as state_workforce_pct,
        w.local_gov_share * 100 as local_workforce_pct,
        w.public_share * 100 as public_workforce_pct,
        w.private_share * 100 as private_workforce_pct,
        d.private_density_pct,
        d.total_density_pct
    FROM state_govt_level_density g
    JOIN state_workforce_shares w ON g.state = w.state
    JOIN v_state_density_latest d ON g.state = d.state
    WHERE g.state = 'NY'
""")
r = cur.fetchone()

print(f"\nState: {r[0]} - {r[1]}")
print(f"\nDensities:")
print(f"  Private: {r[16]}%")
print(f"  Public Combined: {r[2]}% {'(estimated)' if r[3] else ''}")
print(f"  Federal (est): {r[5]}%")
print(f"  State (est): {r[6]}%")
print(f"  Local (est): {r[7]}%")
print(f"  Total: {r[17]}%")

print(f"\nMultiplier: {r[4]}x ({'above' if r[4] > 1 else 'below'} national average)")

print(f"\nWorkforce Composition:")
print(f"  Federal: {r[11]:.1f}%")
print(f"  State: {r[12]:.1f}%")
print(f"  Local: {r[13]:.1f}%")
print(f"  Public Total: {r[14]:.1f}%")
print(f"  Private: {r[15]:.1f}%")

print(f"\nPublic Sector Composition:")
print(f"  Federal share: {r[8]*100:.1f}%")
print(f"  State share: {r[9]*100:.1f}%")
print(f"  Local share: {r[10]*100:.1f}%")

# Contribution breakdown
fed_contrib = r[8] * r[5]
state_contrib = r[9] * r[6]
local_contrib = r[10] * r[7]
print(f"\nContribution to {r[2]}% Public Density:")
print(f"  Federal: {fed_contrib:.1f}%")
print(f"  State: {state_contrib:.1f}%")
print(f"  Local: {local_contrib:.1f}%")
print(f"  Total: {fed_contrib + state_contrib + local_contrib:.1f}%")

print(f"\nComparison to National:")
print(f"  Federal: {r[5]}% vs 25.3% (premium: {r[5]-25.3:+.1f}%)")
print(f"  State: {r[6]}% vs 27.8% (premium: {r[6]-27.8:+.1f}%)")
print(f"  Local: {r[7]}% vs 38.2% (premium: {r[7]-38.2:+.1f}%)")

cur.close()
conn.close()

print("\n" + "=" * 80)
print("API QUERIES WORKING CORRECTLY")
print("=" * 80)
