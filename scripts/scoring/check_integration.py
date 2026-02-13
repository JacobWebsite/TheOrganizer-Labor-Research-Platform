"""Check how govt contracts and sibling union bonus integrate with Phase 2 scoring."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from db_config import get_connection
import psycopg2.extras

conn = get_connection(cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()

# 1. score_govt_contracts distribution
cur.execute("""
    SELECT score_govt_contracts, COUNT(*) as cnt
    FROM mergent_employers WHERE has_union IS NOT TRUE
    GROUP BY score_govt_contracts ORDER BY score_govt_contracts
""")
print("=== score_govt_contracts distribution ===")
for r in cur.fetchall():
    print(f"  {r['score_govt_contracts']}: {r['cnt']:,}")

# 2. sibling_union_bonus distribution
cur.execute("""
    SELECT sibling_union_bonus, COUNT(*) as cnt
    FROM mergent_employers WHERE has_union IS NOT TRUE
    GROUP BY sibling_union_bonus ORDER BY sibling_union_bonus
""")
print("\n=== sibling_union_bonus distribution ===")
for r in cur.fetchall():
    print(f"  {r['sibling_union_bonus']}: {r['cnt']:,}")

# 3. Top by govt contracts
cur.execute("""
    SELECT company_name, state, score_govt_contracts,
           ny_state_contracts, ny_state_contract_value
    FROM mergent_employers
    WHERE has_union IS NOT TRUE AND score_govt_contracts > 0
    ORDER BY score_govt_contracts DESC LIMIT 5
""")
print("\n=== Top 5 by govt contracts score ===")
for r in cur.fetchall():
    name = (r['company_name'] or '')[:40]
    ny_val = r['ny_state_contract_value'] or 0
    print(f"  {name:40s} score={r['score_govt_contracts']}  "
          f"NY_contracts={r['ny_state_contracts']}  NY=${ny_val:,.0f}")

# 4. Top by sibling bonus
cur.execute("""
    SELECT company_name, state, sibling_union_bonus, score_union_presence,
           score_union_presence_reason
    FROM mergent_employers
    WHERE has_union IS NOT TRUE AND sibling_union_bonus > 0
    ORDER BY sibling_union_bonus DESC LIMIT 5
""")
print("\n=== Top 5 by sibling_union_bonus ===")
for r in cur.fetchall():
    name = (r['company_name'] or '')[:40]
    print(f"  {name:40s} bonus={r['sibling_union_bonus']}  "
          f"presence={r['score_union_presence']}  "
          f"reason={r['score_union_presence_reason']}")

# 5. Coverage
cur.execute("""
    SELECT
        COUNT(*) FILTER (WHERE score_govt_contracts > 0) as has_govt,
        COUNT(*) FILTER (WHERE sibling_union_bonus > 0) as has_sibling,
        COUNT(*) FILTER (WHERE score_govt_contracts > 0 AND sibling_union_bonus > 0) as has_both,
        COUNT(*) as total
    FROM mergent_employers WHERE has_union IS NOT TRUE
""")
r = cur.fetchone()
print(f"\n=== Coverage ===")
print(f"  Has govt contracts score: {r['has_govt']:,} / {r['total']:,} ({r['has_govt']*100//r['total']}%)")
print(f"  Has sibling union bonus:  {r['has_sibling']:,} / {r['total']:,} ({r['has_sibling']*100//r['total']}%)")
print(f"  Has both:                 {r['has_both']:,}")

# 6. Check the API scorecard - what happens with contracts
print("\n=== API Scorecard: score_contracts in list endpoint ===")
print("  List endpoint (/api/organizing/scorecard): score_contracts = 0 (HARDCODED)")
print("  Detail endpoint (/api/organizing/scorecard/{id}): looks up NY + NYC contracts")
print("  -> GAP: list endpoint doesn't score contracts at all")

# 7. Check how sibling_union_bonus was populated
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'mergent_employers'
    AND column_name LIKE '%sibling%' OR column_name LIKE '%union_pres%'
    ORDER BY column_name
""")
print(f"\n=== Sibling/union presence columns on mergent_employers ===")
for r in cur.fetchall():
    print(f"  {r['column_name']}")

# 8. Check if the API sibling endpoint feeds into stored scores
print("\n=== API Sibling endpoint integration ===")
print("  GET /api/organizing/siblings/{estab_id} - returns similar F7 employers")
print("  BUT: This operates on OSHA establishments, not mergent_employers")
print("  -> GAP: sibling_union_bonus on mergent was populated separately")
print("         (by fix_sibling_bonus.py), not by the new API endpoint")

# 9. What does fix_sibling_bonus actually do?
print("\n=== How sibling_union_bonus was originally populated ===")
cur.execute("""
    SELECT score_union_presence_reason, COUNT(*) as cnt
    FROM mergent_employers
    WHERE has_union IS NOT TRUE AND sibling_union_bonus > 0
    GROUP BY score_union_presence_reason
    ORDER BY cnt DESC LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {r['score_union_presence_reason']}: {r['cnt']:,}")

cur.close()
conn.close()
