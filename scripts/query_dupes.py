"""Query mergent_employers duplicate groups for manual review."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import psycopg2, psycopg2.extras
from db_config import get_connection

conn = get_connection()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

cur.execute("""
    WITH dupes AS (
        SELECT UPPER(TRIM(company_name)) as norm_name, state,
               COUNT(*) as cnt
        FROM mergent_employers
        GROUP BY UPPER(TRIM(company_name)), state
        HAVING COUNT(*) > 1
    )
    SELECT m.id, m.company_name, m.state, m.city,
           m.employees_site, m.employees_all_sites, m.sales_amount,
           m.naics_primary, m.has_union, m.duns,
           m.year_founded, m.company_type, m.subsidiary_status,
           m.matched_f7_employer_id, m.similarity_score
    FROM mergent_employers m
    JOIN dupes d ON UPPER(TRIM(m.company_name)) = d.norm_name AND m.state = d.state
    ORDER BY UPPER(TRIM(m.company_name)), m.state, m.id
""")
rows = cur.fetchall()
print(f"Total duplicate rows: {len(rows)}")

from collections import defaultdict
groups = defaultdict(list)
for r in rows:
    key = (r['company_name'].strip().upper(), r['state'])
    groups[key].append(r)

print(f"Total groups: {len(groups)}")
print("---")

for i, ((name, state), members) in enumerate(sorted(groups.items(), key=lambda x: -len(x[1]))):
    union_any = any(m['has_union'] for m in members)
    f7_any = any(m['matched_f7_employer_id'] for m in members)
    print(f"\nGROUP {i+1}: {name} ({state}) - {len(members)} records | union={union_any} | f7={f7_any}")
    for m in members:
        u = 'UNION' if m['has_union'] else 'no-union'
        f7 = "f7=%s" % m['matched_f7_employer_id'] if m['matched_f7_employer_id'] else 'no-f7'
        emp = m['employees_site'] if m['employees_site'] else '?'
        emp_total = m['employees_all_sites'] if m['employees_all_sites'] else '?'
        sales = m['sales_amount']
        if sales:
            rev = "$%.1fM" % (float(sales) / 1e6)
        else:
            rev = "?"
        sim_val = m['similarity_score']
        sim = "sim=%.3f" % sim_val if sim_val is not None else "sim=n/a"
        naics = m['naics_primary'] or '?'
        city = m['city'] or '?'
        founded = m['year_founded'] or '?'
        sub = 'subsidiary' if m['subsidiary_status'] else 'HQ'
        duns = m['duns'] or '?'
        print(f"  id={m['id']:>6} DUNS={duns:>11} {city:<20} emp={emp!s:>6}/{emp_total!s:>6} rev={rev:>10} NAICS={naics:<8} {u:<8} {f7:<12} {sim:<12} {sub} yr={founded}")

conn.close()
