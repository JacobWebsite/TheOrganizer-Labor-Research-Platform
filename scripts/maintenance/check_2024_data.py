import os
import psycopg2
from db_config import get_connection
conn = get_connection()
cur = conn.cursor()

# Use 2024 data for complete picture
print("USING 2024 DATA (more complete than 2025)")
print("=" * 90)

# Check IBT 2024
print("\nIBT (Teamsters) - 2024 filings:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, state
    FROM lm_data
    WHERE aff_abbr = 'IBT'
    AND yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 15
""")
total = 0
for r in cur.fetchall():
    total += r[2] or 0
    print(f"  {r[0]:<12} {(r[1] or '')[:40]:<42} {r[2] or 0:>10,} ${r[3] or 0:>14,.0f}")

cur.execute("SELECT COUNT(*), SUM(members) FROM lm_data WHERE aff_abbr = 'IBT' AND yr_covered = 2024")
r = cur.fetchone()
print(f"\n  IBT 2024: {r[0]} filings, {r[1] or 0:,} total members")

# Check UAW 2024
print("\n\nUAW - 2024 filings:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, state
    FROM lm_data
    WHERE aff_abbr = 'UAW'
    AND yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {(r[1] or '')[:40]:<42} {r[2] or 0:>10,} ${r[3] or 0:>14,.0f}")

cur.execute("SELECT COUNT(*), SUM(members) FROM lm_data WHERE aff_abbr = 'UAW' AND yr_covered = 2024")
r = cur.fetchone()
print(f"\n  UAW 2024: {r[0]} filings, {r[1] or 0:,} total members")

# Check UFCW 2024
print("\n\nUFCW - 2024 filings:")
cur.execute("""
    SELECT f_num, union_name, members, ttl_receipts, state
    FROM lm_data
    WHERE aff_abbr = 'UFCW'
    AND yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 15
""")
for r in cur.fetchall():
    print(f"  {r[0]:<12} {(r[1] or '')[:40]:<42} {r[2] or 0:>10,} ${r[3] or 0:>14,.0f}")

cur.execute("SELECT COUNT(*), SUM(members) FROM lm_data WHERE aff_abbr = 'UFCW' AND yr_covered = 2024")
r = cur.fetchone()
print(f"\n  UFCW 2024: {r[0]} filings, {r[1] or 0:,} total members")

# Full comparison for 2024
print("\n" + "=" * 90)
print("OLMS 2024 DATA vs PUBLISHED MEMBERSHIP")
print("=" * 90)

published = {
    'AFSCME': 1400000,
    'SEIU': 2000000,
    'NEA': 2900000,
    'AFT': 1700000,
    'IAFF': 340000,
    'IBT': 1300000,
    'UFCW': 1300000,
    'UAW': 400000,
    'USW': 850000,
    'CWA': 700000,
    'IBEW': 775000,
}

print(f"{'Union':<12} {'OLMS 2024':>14} {'Published':>12} {'Gap':>12} {'Coverage':>10}")
print("-" * 70)

for union, pub in published.items():
    cur.execute("""
        SELECT SUM(members) FROM lm_data 
        WHERE aff_abbr = %s AND yr_covered = 2024
    """, (union,))
    olms = cur.fetchone()[0] or 0
    gap = pub - olms
    pct = (olms / pub * 100) if pub > 0 else 0
    print(f"{union:<12} {olms:>14,} {pub:>12,} {gap:>+12,} {pct:>9.1f}%")

conn.close()
