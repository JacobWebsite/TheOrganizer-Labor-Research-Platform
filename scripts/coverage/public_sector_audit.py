import os
import psycopg2

conn = psycopg2.connect(
    host="localhost", 
    dbname="olms_multiyear", 
    user="postgres", 
    password="os.environ.get('DB_PASSWORD', '')"
)
cur = conn.cursor()

print("=" * 80)
print("PUBLIC SECTOR UNION MEMBERSHIP AUDIT")
print("=" * 80)

# Define public sector affiliations by category
federal_affs = ['AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE', 'NRLCA', 'NPMHU']
teachers_affs = ['NEA', 'AFT']
state_local_affs = ['AFSCME', 'FOP', 'IAFF', 'PBA']
mixed_affs = ['SEIU', 'CWA']  # Have both public and private members

print("\n1. FEDERAL EMPLOYEE UNIONS (2024 filings)")
print("-" * 60)

cur.execute("""
    SELECT aff_abbr, COUNT(*) as cnt, COALESCE(SUM(members), 0) as mem
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = ANY(%s)
    GROUP BY aff_abbr ORDER BY mem DESC;
""", (federal_affs,))

fed_total = 0
for row in cur.fetchall():
    print(f"  {row[0]:10} {row[1]:5} locals   {row[2]:>12,.0f} members")
    fed_total += row[2]
print(f"  {'TOTAL':10} {'':5}        {fed_total:>12,.0f} members")

print("\n2. TEACHER UNIONS (2024 filings)")
print("-" * 60)

cur.execute("""
    SELECT aff_abbr, COUNT(*) as cnt, COALESCE(SUM(members), 0) as mem
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = ANY(%s)
    GROUP BY aff_abbr ORDER BY mem DESC;
""", (teachers_affs,))

teacher_total = 0
for row in cur.fetchall():
    print(f"  {row[0]:10} {row[1]:5} locals   {row[2]:>12,.0f} members")
    teacher_total += row[2]
print(f"  {'TOTAL':10} {'':5}        {teacher_total:>12,.0f} members")

print("\n3. STATE/LOCAL GOVERNMENT UNIONS (2024 filings)")
print("-" * 60)

cur.execute("""
    SELECT aff_abbr, COUNT(*) as cnt, COALESCE(SUM(members), 0) as mem
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = ANY(%s)
    GROUP BY aff_abbr ORDER BY mem DESC;
""", (state_local_affs,))

statelocal_total = 0
for row in cur.fetchall():
    print(f"  {row[0]:10} {row[1]:5} locals   {row[2]:>12,.0f} members")
    statelocal_total += row[2]
print(f"  {'TOTAL':10} {'':5}        {statelocal_total:>12,.0f} members")

print("\n4. MIXED PUBLIC/PRIVATE UNIONS (2024 filings)")
print("-" * 60)

cur.execute("""
    SELECT aff_abbr, COUNT(*) as cnt, COALESCE(SUM(members), 0) as mem
    FROM lm_data
    WHERE yr_covered = 2024 AND aff_abbr = ANY(%s)
    GROUP BY aff_abbr ORDER BY mem DESC;
""", (mixed_affs,))

mixed_total = 0
for row in cur.fetchall():
    print(f"  {row[0]:10} {row[1]:5} locals   {row[2]:>12,.0f} members")
    mixed_total += row[2]
print(f"  {'TOTAL':10} {'':5}        {mixed_total:>12,.0f} members")
print("  (Note: SEIU ~40% public, CWA ~25% public)")

print("\n" + "=" * 80)
print("SUMMARY: PUBLIC SECTOR COVERAGE")
print("=" * 80)

# Estimate public sector portions of mixed unions
seiu_public_est = mixed_total * 0.35  # Conservative estimate

raw_public_total = fed_total + teacher_total + statelocal_total
adjusted_public_total = raw_public_total + seiu_public_est

print(f"""
RAW OLMS TOTALS (includes double-counting):
  Federal employees:      {fed_total:>12,.0f}
  Teachers (NEA+AFT):     {teacher_total:>12,.0f}
  State/Local (AFSCME+):  {statelocal_total:>12,.0f}
  -------------------------------------------
  Subtotal:               {raw_public_total:>12,.0f}
  
  Mixed unions (SEIU/CWA): {mixed_total:>12,.0f}
  Est. public portion:    {seiu_public_est:>12,.0f} (~35%)
  -------------------------------------------
  RAW TOTAL:              {raw_public_total + seiu_public_est:>12,.0f}

ADJUSTMENTS NEEDED:
  - NEA/AFT overlap (dual affiliates): subtract ~900K
  - Federation double-counting: subtract ~10-15%
  
ESTIMATED US PUBLIC SECTOR: ~{(raw_public_total + seiu_public_est) * 0.85 - 900000:,.0f}

BLS BENCHMARK: ~7,000,000 public sector union members
""")

# Now let's look at largest public sector locals
print("\n" + "=" * 80)
print("TOP 20 PUBLIC SECTOR UNION LOCALS (2024)")
print("=" * 80)

all_public_affs = federal_affs + teachers_affs + state_local_affs

cur.execute("""
    SELECT aff_abbr, union_name, unit_name, state, members
    FROM lm_data
    WHERE yr_covered = 2024 
    AND aff_abbr = ANY(%s)
    AND members IS NOT NULL
    ORDER BY members DESC
    LIMIT 20;
""", (all_public_affs,))

print(f"{'Aff':8} {'State':5} {'Members':>12}  Name")
print("-" * 80)
for row in cur.fetchall():
    aff, name, unit, state, members = row
    display_name = unit if unit else name
    display_name = display_name[:50] if display_name else 'N/A'
    print(f"{aff:8} {state or 'NA':5} {members:>12,.0f}  {display_name}")

conn.close()
