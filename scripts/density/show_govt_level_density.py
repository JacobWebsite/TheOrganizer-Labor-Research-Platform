import os
from db_config import get_connection
"""Display decomposed government-level union density for all states"""
import psycopg2

conn = get_connection()
cur = conn.cursor()

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
""")

print("=" * 105)
print("ESTIMATED UNION DENSITY BY GOVERNMENT LEVEL - ALL STATES")
print("=" * 105)
print(f"National Baseline (2024): Federal 25.3%, State Gov 27.8%, Local Gov 38.2%")
print()
print(f"{'State':5} | {'State Name':22} | {'Public':7} | {'Est':3} | {'k':5} | {'Federal':8} | {'State':8} | {'Local':8}")
print(f"{'-'*5} | {'-'*22} | {'-'*7} | {'-'*3} | {'-'*5} | {'-'*8} | {'-'*8} | {'-'*8}")

for row in cur.fetchall():
    state = row[0]
    name = (row[1] or '')[:22]
    pub = row[2]
    est = '*' if row[3] else ''
    k = row[4]
    fed = row[5]
    st = row[6]
    loc = row[7]
    print(f"{state:5} | {name:22} | {pub:6.1f}% | {est:3} | {k:5.2f} | {fed:7.1f}% | {st:7.1f}% | {loc:7.1f}%")

print("=" * 105)
print("* = Public density estimated from total/private (small CPS sample)")
print(f"k = State's union premium vs national (1.0 = same as national average)")

# Show regional patterns
print("\n" + "=" * 105)
print("REGIONAL PATTERNS")
print("=" * 105)

# High union states (k > 1.5)
cur.execute("""
    SELECT state, multiplier, est_local_density
    FROM state_govt_level_density WHERE multiplier > 1.5
    ORDER BY multiplier DESC
""")
high = cur.fetchall()
print(f"\nHIGH UNION STATES (k > 1.5x national): {len(high)} states")
print(f"  {', '.join([r[0] for r in high])}")

# Medium union states (0.75 < k <= 1.5)
cur.execute("""
    SELECT state, multiplier
    FROM state_govt_level_density WHERE multiplier > 0.75 AND multiplier <= 1.5
    ORDER BY multiplier DESC
""")
med = cur.fetchall()
print(f"\nMEDIUM UNION STATES (0.75-1.5x national): {len(med)} states")
print(f"  {', '.join([r[0] for r in med])}")

# Low union states (k <= 0.75)
cur.execute("""
    SELECT state, multiplier
    FROM state_govt_level_density WHERE multiplier <= 0.75
    ORDER BY multiplier DESC
""")
low = cur.fetchall()
print(f"\nLOW UNION STATES (< 0.75x national): {len(low)} states")
print(f"  {', '.join([r[0] for r in low])}")

# Extreme examples
print("\n" + "=" * 105)
print("EXTREME COMPARISONS")
print("=" * 105)

cur.execute("""
    SELECT state, est_local_density FROM state_govt_level_density
    ORDER BY est_local_density DESC LIMIT 1
""")
highest = cur.fetchone()

cur.execute("""
    SELECT state, est_local_density FROM state_govt_level_density
    ORDER BY est_local_density ASC LIMIT 1
""")
lowest = cur.fetchone()

print(f"\nLocal Government Density Range:")
print(f"  Highest: {highest[0]} at {highest[1]:.1f}%")
print(f"  Lowest:  {lowest[0]} at {lowest[1]:.1f}%")
print(f"  Ratio:   {highest[1]/lowest[1]:.1f}x difference")

cur.close()
conn.close()
