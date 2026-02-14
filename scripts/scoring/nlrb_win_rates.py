"""
NLRB Election Win Rates by State
Explores nlrb_elections and nlrb_participants tables, then calculates
union win rates by state for elections since 2020.
"""
import psycopg2
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# ---- 1. NLRB tables ----
print("=" * 70)
print("NLRB TABLE DISCOVERY")
print("=" * 70)
cur.execute("SELECT table_name FROM information_schema.tables WHERE table_name LIKE '%%nlrb%%' ORDER BY table_name")
tables = cur.fetchall()
print(f"\nNLRB tables found: {len(tables)}")
for t in tables:
    print(f"  {t[0]}")

# ---- 2. nlrb_elections schema ----
print("\n" + "=" * 70)
print("nlrb_elections COLUMNS")
print("=" * 70)
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'nlrb_elections'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(f"  {r[0]:40s} {r[1]}")

# ---- 3. nlrb_participants schema ----
print("\n" + "=" * 70)
print("nlrb_participants COLUMNS")
print("=" * 70)
cur.execute("""
    SELECT column_name, data_type
    FROM information_schema.columns
    WHERE table_name = 'nlrb_participants'
    ORDER BY ordinal_position
""")
for r in cur.fetchall():
    print(f"  {r[0]:40s} {r[1]}")

# ---- 4. Check union_won values ----
print("\n" + "=" * 70)
print("DISTINCT union_won VALUES")
print("=" * 70)
cur.execute("SELECT DISTINCT union_won FROM nlrb_elections LIMIT 20")
for r in cur.fetchall():
    print(f"  {repr(r[0])}")

# ---- 5. Row counts ----
print("\n" + "=" * 70)
print("ROW COUNTS")
print("=" * 70)
cur.execute("SELECT COUNT(*) FROM nlrb_elections")
print(f"  nlrb_elections:     {cur.fetchone()[0]:,}")
cur.execute("SELECT COUNT(*) FROM nlrb_participants")
print(f"  nlrb_participants:  {cur.fetchone()[0]:,}")

# ---- 6. Valid 2-letter state codes ----
print("\n" + "=" * 70)
print("VALID STATE CODES IN nlrb_participants")
print("=" * 70)
cur.execute("""
    SELECT DISTINCT state
    FROM nlrb_participants
    WHERE state ~ '^[A-Z]{2}$'
    ORDER BY state
""")
states = [r[0] for r in cur.fetchall()]
print(f"  Count: {len(states)}")
print(f"  States: {', '.join(states)}")

# ---- 7. Date range check ----
print("\n" + "=" * 70)
print("ELECTION DATE RANGE")
print("=" * 70)
cur.execute("SELECT MIN(election_date), MAX(election_date) FROM nlrb_elections WHERE election_date IS NOT NULL")
row = cur.fetchone()
print(f"  Earliest: {row[0]}")
print(f"  Latest:   {row[1]}")

# ---- 8. Win rates by state (2020+) ----
print("\n" + "=" * 70)
print("NLRB ELECTION WIN RATES BY STATE (2020-01-01 onward, >= 5 elections)")
print("=" * 70)

# Determine the right condition for union_won
# First check if it's boolean or text
cur.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'nlrb_elections' AND column_name = 'union_won'")
dtype = cur.fetchone()
if dtype:
    print(f"\n  union_won data type: {dtype[0]}")

# Build query -- handle both boolean and text cases
# If boolean: union_won = true
# If text: union_won IN ('true','True','Yes','Won','1')
cur.execute("""
    SELECT p.state,
           COUNT(DISTINCT e.case_number) AS total_elections,
           COUNT(DISTINCT CASE WHEN e.union_won::text IN ('true','True','t','1','Won','Yes')
                                THEN e.case_number END) AS union_wins,
           ROUND(
               COUNT(DISTINCT CASE WHEN e.union_won::text IN ('true','True','t','1','Won','Yes')
                                    THEN e.case_number END) * 100.0
               / NULLIF(COUNT(DISTINCT e.case_number), 0), 1
           ) AS win_rate_pct
    FROM nlrb_elections e
    JOIN nlrb_participants p ON e.case_number = p.case_number
    WHERE p.state ~ '^[A-Z]{2}$'
      AND e.election_date >= '2020-01-01'
    GROUP BY p.state
    HAVING COUNT(DISTINCT e.case_number) >= 5
    ORDER BY win_rate_pct DESC
""")

rows = cur.fetchall()
print(f"\n  {'State':<7} {'Elections':>10} {'Wins':>8} {'Win Rate':>10}")
print(f"  {'-'*5:<7} {'-'*10:>10} {'-'*8:>8} {'-'*10:>10}")
total_elec = 0
total_wins = 0
for r in rows:
    state, elections, wins, rate = r
    total_elec += elections
    total_wins += wins
    print(f"  {state:<7} {elections:>10,} {wins:>8,} {rate:>9.1f}%")

print(f"  {'-'*5:<7} {'-'*10:>10} {'-'*8:>8} {'-'*10:>10}")
overall = round(total_wins * 100.0 / total_elec, 1) if total_elec else 0
print(f"  {'TOTAL':<7} {total_elec:>10,} {total_wins:>8,} {overall:>9.1f}%")
print(f"\n  States with >= 5 elections: {len(rows)}")

# ---- 9. National summary ----
print("\n" + "=" * 70)
print("NATIONAL SUMMARY (all elections 2020+)")
print("=" * 70)
cur.execute("""
    SELECT COUNT(*) AS total,
           SUM(CASE WHEN union_won::text IN ('true','True','t','1','Won','Yes') THEN 1 ELSE 0 END) AS wins
    FROM nlrb_elections
    WHERE election_date >= '2020-01-01'
""")
row = cur.fetchone()
if row and row[0]:
    print(f"  Total elections:  {row[0]:,}")
    print(f"  Union wins:       {row[1]:,}")
    print(f"  Win rate:         {round(row[1]*100.0/row[0], 1)}%")

conn.close()
print("\nDone.")
