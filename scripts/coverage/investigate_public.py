import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 80)
print("INVESTIGATING MEMBERSHIP REPORTING PATTERNS")
print("=" * 80)

# Check top filings by members to understand what's happening
print("\n1. TOP 20 FILINGS BY MEMBERSHIP (2024)")
print("-" * 80)

cur.execute("""
    SELECT aff_abbr, union_name, unit_name, state, COALESCE(members,0), form_type
    FROM lm_data
    WHERE yr_covered = 2024
    ORDER BY members DESC NULLS LAST
    LIMIT 20;
""")

print(f"{'Aff':8} {'State':5} {'Type':5} {'Members':>12}  Name")
print("-" * 80)
for row in cur.fetchall():
    aff, name, unit, state, members, form = row
    display = (unit if unit else name)[:45]
    print(f"{aff or 'N/A':8} {state or 'NA':5} {form:5} {members:>12,.0f}  {display}")

# Now let's look specifically at public sector unions
print("\n2. ALL PUBLIC SECTOR UNION FILINGS - TOP MEMBERS")
print("-" * 80)

public_affs = ['AFSCME','NEA','AFT','AFGE','APWU','NALC','NFFE','NTEU','FOP','IAFF','PBA','NAGE','NRLCA','NPMHU']

cur.execute("""
    SELECT aff_abbr, union_name, unit_name, state, COALESCE(members,0), form_type
    FROM lm_data
    WHERE yr_covered = 2024
    AND aff_abbr = ANY(%s)
    AND members > 0
    ORDER BY members DESC
    LIMIT 30;
""", (public_affs,))

print(f"{'Aff':8} {'State':5} {'Type':5} {'Members':>12}  Name")
print("-" * 80)
for row in cur.fetchall():
    aff, name, unit, state, members, form = row
    display = (unit if unit else name)[:45]
    print(f"{aff:8} {state or 'NA':5} {form:5} {members:>12,.0f}  {display}")

# Get totals using the BIGGEST filer per affiliation
print("\n3. LARGEST FILING PER PUBLIC SECTOR AFFILIATION")
print("-" * 80)

cur.execute("""
    WITH ranked AS (
        SELECT 
            aff_abbr,
            union_name,
            unit_name,
            state,
            members,
            form_type,
            ROW_NUMBER() OVER (PARTITION BY aff_abbr ORDER BY members DESC NULLS LAST) as rn
        FROM lm_data
        WHERE yr_covered = 2024
        AND aff_abbr = ANY(%s)
    )
    SELECT aff_abbr, union_name, unit_name, state, COALESCE(members,0), form_type
    FROM ranked
    WHERE rn = 1
    ORDER BY members DESC NULLS LAST;
""", (public_affs,))

total = 0
print(f"{'Aff':8} {'State':5} {'Type':5} {'Members':>12}  Name")
print("-" * 80)
for row in cur.fetchall():
    aff, name, unit, state, members, form = row
    display = (unit if unit else name)[:45]
    print(f"{aff:8} {state or 'NA':5} {form:5} {members:>12,.0f}  {display}")
    total += members

print("-" * 80)
print(f"{'TOTAL':8} {'':5} {'':5} {total:>12,.0f}")

# Now let's check the suspicious MT AFT filing
print("\n4. INVESTIGATING THE SUSPICIOUS MT AFT FILING")
print("-" * 80)

cur.execute("""
    SELECT union_name, unit_name, state, city, members, form_type, f_num
    FROM lm_data
    WHERE yr_covered = 2024
    AND state = 'MT'
    AND aff_abbr = 'AFT'
    ORDER BY members DESC;
""")

for row in cur.fetchall():
    print(row)

# Check if that's a data quality issue
print("\n5. ALL AFT FILINGS > 500K MEMBERS")
print("-" * 80)

cur.execute("""
    SELECT union_name, unit_name, state, city, members, form_type
    FROM lm_data
    WHERE yr_covered = 2024
    AND aff_abbr = 'AFT'
    AND members > 500000
    ORDER BY members DESC;
""")

for row in cur.fetchall():
    print(row)

conn.close()
