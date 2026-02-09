import os
"""
Update form_990_estimates with VERIFIED dues revenue figures
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='os.environ.get('DB_PASSWORD', '')')
cur = conn.cursor()

print("Updating form_990_estimates with verified data...")

# AFSCME: Real dues revenue is $177.7M (2022) not $320M
# Using 2023 data: $207M total revenue, 86% from dues = ~$178M dues
cur.execute("""
    UPDATE form_990_estimates
    SET dues_revenue = 177700000,
        estimated_members = ROUND(177700000 / dues_rate_used),
        dues_rate_source = 'VERIFIED: LM-2 data via Mackinac Center - $177.7M dues (2022)'
    WHERE organization_name = 'AFSCME International'
""")
print(f"  AFSCME International updated: {cur.rowcount} rows")

# SEIU: Real total revenue is $287.9M (2023)
# This is the LM-2 filing data
cur.execute("""
    UPDATE form_990_estimates
    SET dues_revenue = 287900000,
        estimated_members = ROUND(287900000 / dues_rate_used),
        dues_rate_source = 'VERIFIED: LM-2 data via Americans for Fair Treatment - $287.9M (2023)'
    WHERE organization_name = 'SEIU International'
""")
print(f"  SEIU International updated: {cur.rowcount} rows")

conn.commit()

# Show updated values
print("\nUpdated form_990_estimates (national orgs):")
cur.execute("""
    SELECT organization_name, dues_revenue, dues_rate_used, estimated_members, dues_rate_source
    FROM form_990_estimates
    WHERE org_type LIKE '%NATIONAL%'
    ORDER BY estimated_members DESC
""")

print(f"{'Organization':<45} {'Dues':>15} {'Rate':>10} {'Members':>12}")
print("-" * 90)
for r in cur.fetchall():
    name, dues, rate, members, source = r
    print(f"{name[:43]:<45} ${float(dues):>13,.0f} ${float(rate):>8.2f} {members:>12,}")
    print(f"  Source: {source[:75]}")

conn.close()
