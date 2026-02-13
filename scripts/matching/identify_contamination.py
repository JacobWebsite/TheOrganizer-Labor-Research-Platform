import os
"""
Clean up contamination in private sector employer data
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password=os.environ.get('DB_PASSWORD', ''))
conn.autocommit = True
cur = conn.cursor()

print("=" * 80)
print("DATA CLEANUP: Identifying Private Sector Contamination")
print("=" * 80)

# 1. Identify federal/public sector employers in private sector data
print("\n--- Federal/Public Sector Contamination ---")
cur.execute("""
    SELECT employer_name, reconciled_workers, affiliation, match_type
    FROM v_f7_reconciled_private_sector
    WHERE 
        employer_name ILIKE '%veteran%affairs%'
        OR employer_name ILIKE '%postal service%'
        OR employer_name ILIKE '%department of%'
        OR employer_name ILIKE '%state of %'
        OR employer_name ILIKE '%city of %'
        OR employer_name ILIKE '%county of %'
        OR employer_name ILIKE '%HUD/%'
        OR employer_name ILIKE '%social security%'
        OR employer_name ILIKE '%federal%'
        OR affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'NAGE')
    ORDER BY reconciled_workers DESC
    LIMIT 30;
""")
print(f"{'Employer':<50} {'Workers':>10} {'Union':<10} {'Type'}")
print("-" * 85)
fed_total = 0
for r in cur.fetchall():
    print(f"{(r[0] or 'Unknown')[:50]:<50} {r[1] or 0:>10,.0f} {r[2] or 'N/A':<10} {r[3]}")
    fed_total += r[1] or 0
print(f"\nTotal federal contamination identified: {fed_total:,.0f} workers")

# 2. Identify suspicious SAG-AFTRA entries (likely multi-employer or misclassified)
print("\n--- SAG-AFTRA Suspicious Entries ---")
cur.execute("""
    SELECT employer_name, reconciled_workers, match_type
    FROM v_f7_reconciled_private_sector
    WHERE affiliation = 'SAGAFTRA'
    ORDER BY reconciled_workers DESC
    LIMIT 20;
""")
print(f"{'Employer':<55} {'Workers':>10} {'Type'}")
print("-" * 75)
sag_total = 0
for r in cur.fetchall():
    print(f"{(r[0] or 'Unknown')[:55]:<55} {r[1] or 0:>10,.0f} {r[2]}")
    sag_total += r[1] or 0
print(f"\nTotal SAG-AFTRA in top 20: {sag_total:,.0f}")

# 3. Check "All Signatories" entries (these are multi-employer placeholders)
print("\n--- Multi-Employer Placeholders (Signatories) ---")
cur.execute("""
    SELECT employer_name, reconciled_workers, affiliation
    FROM v_f7_reconciled_private_sector
    WHERE employer_name ILIKE '%signator%'
    ORDER BY reconciled_workers DESC
    LIMIT 15;
""")
sig_total = 0
for r in cur.fetchall():
    print(f"  {(r[0] or 'Unknown')[:55]:<55} {r[1] or 0:>10,.0f} {r[2]}")
    sig_total += r[1] or 0
print(f"\nTotal 'Signatories' placeholder workers: {sig_total:,.0f}")

# 4. Check UNKNOWN affiliation (often problematic)
print("\n--- UNKNOWN Affiliation Analysis ---")
cur.execute("""
    SELECT 
        COUNT(*) as count,
        SUM(reconciled_workers) as total_workers,
        AVG(reconciled_workers) as avg_workers
    FROM v_f7_reconciled_private_sector
    WHERE affiliation = 'UNKNOWN' OR affiliation IS NULL;
""")
r = cur.fetchone()
print(f"UNKNOWN records: {r[0]:,}, Total workers: {r[1] or 0:,.0f}, Avg: {r[2] or 0:,.0f}")

cur.execute("""
    SELECT employer_name, reconciled_workers
    FROM v_f7_reconciled_private_sector
    WHERE (affiliation = 'UNKNOWN' OR affiliation IS NULL)
    AND reconciled_workers > 10000
    ORDER BY reconciled_workers DESC;
""")
print("\nLarge UNKNOWN employers (>10K workers):")
for r in cur.fetchall():
    print(f"  {(r[0] or 'Unknown')[:55]:<55} {r[1] or 0:>10,.0f}")

conn.close()
