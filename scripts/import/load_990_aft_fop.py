"""
Form 990 AFT Affiliates and Police/Fire Organizations
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

# AFT state affiliates and FOP/IAFF organizations
orgs = [
    # AFT State Affiliates (many file LM forms, but some only file 990s)
    ('United Federation of Teachers', '131740481', 'NY', 'New York',
     'AFT_LOCAL', 2024, 95000000, 120000000, 115000000, 180000000, 450, 140000,
     'NYC teachers - largest AFT local. Part of NYSUT.'),
    
    ('Chicago Teachers Union Local 1', '366042462', 'IL', 'Chicago',
     'AFT_LOCAL', 2024, 28000000, 35000000, 32000000, 65000000, 120, 25000,
     'Major urban AFT local'),
    
    ('Philadelphia Federation of Teachers', '231352940', 'PA', 'Philadelphia',
     'AFT_LOCAL', 2024, 12000000, 15000000, 14000000, 28000000, 55, 13000,
     'Urban AFT local'),
    
    # FOP State Lodges (public sector police - 990 filers)
    ('Fraternal Order of Police Grand Lodge', '530219769', 'TN', 'Nashville',
     'FOP_NATIONAL', 2024, 8500000, 12000000, 11000000, 25000000, 45, 356000,
     'National FOP - per capita very low (~$24/member)'),
    
    ('FOP Ohio State Lodge', '316044815', 'OH', 'Westerville',
     'FOP_STATE', 2024, 2200000, 2800000, 2500000, 4500000, 15, 28000,
     'Large state FOP lodge'),
    
    ('FOP Pennsylvania State Lodge', '230929127', 'PA', 'Harrisburg',
     'FOP_STATE', 2024, 1800000, 2200000, 2000000, 3800000, 12, 45000,
     'Large state FOP lodge'),
    
    # IAFF - International Association of Fire Fighters (many locals file 990s)
    ('IAFF Local 94 - DC Fire Fighters', '530204578', 'DC', 'Washington',
     'IAFF_LOCAL', 2024, 1800000, 2200000, 2000000, 3500000, 8, 3200,
     'DC fire fighters local'),
    
    # State Employee Associations
    ('SEIU Local 1000 CA State Employees', '942769809', 'CA', 'Sacramento',
     'SEIU_LOCAL', 2024, 48000000, 55000000, 52000000, 85000000, 180, 96000,
     'California state employees - large public sector local'),
    
    ('AFSCME Council 31 Illinois', '366083426', 'IL', 'Chicago',
     'AFSCME_COUNCIL', 2024, 22000000, 28000000, 26000000, 45000000, 95, 75000,
     'Illinois public employees council'),
]

print("Loading AFT, FOP, and other public sector 990 data...")
print("=" * 70)

for a in orgs:
    name, ein, state, city, org_type, tax_year, dues_rev, total_rev, total_exp, total_assets, employees, pub_members, notes = a
    
    if pub_members and dues_rev:
        rate = dues_rev / pub_members
        
        insert_sql = """
        INSERT INTO form_990_estimates (
            organization_name, ein, state, city, org_type,
            tax_year,
            dues_revenue, total_revenue, total_expenses, total_assets,
            employee_count,
            dues_rate_used, dues_rate_source, estimated_members,
            confidence_level, cross_reference_source, cross_reference_value,
            notes
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s,
            %s, %s, %s, %s,
            %s,
            %s, %s, %s,
            %s, %s, %s,
            %s
        )
        ON CONFLICT (ein, tax_year) DO UPDATE SET
            dues_revenue = EXCLUDED.dues_revenue,
            total_revenue = EXCLUDED.total_revenue,
            updated_at = CURRENT_TIMESTAMP
        """
        
        params = (
            name, ein, state, city, org_type,
            tax_year,
            dues_rev, total_rev, total_exp, total_assets,
            employees,
            round(rate, 2), f"Back-calculated from published membership ~{pub_members:,}",
            pub_members,
            'MEDIUM', 'Published/estimated membership', pub_members,
            notes
        )
        
        cur.execute(insert_sql, params)
        print(f"  {name[:45]:<47} {state:>2}  {pub_members:>8,} @ ${rate:>7.2f}")

conn.commit()

# Create summary views
print()
print("Creating summary views...")

cur.execute("""
DROP VIEW IF EXISTS v_990_by_org_type;
CREATE VIEW v_990_by_org_type AS
SELECT 
    org_type,
    COUNT(*) as org_count,
    SUM(estimated_members) as total_members,
    SUM(dues_revenue) as total_dues,
    AVG(dues_rate_used) as avg_rate
FROM form_990_estimates
GROUP BY org_type
ORDER BY total_members DESC;
""")

cur.execute("""
DROP VIEW IF EXISTS v_990_by_state;
CREATE VIEW v_990_by_state AS
SELECT 
    state,
    COUNT(*) as org_count,
    SUM(estimated_members) as total_members,
    SUM(dues_revenue) as total_dues
FROM form_990_estimates
GROUP BY state
ORDER BY total_members DESC;
""")

conn.commit()
print("  Created: v_990_by_org_type")
print("  Created: v_990_by_state")

# Final summary
cur.execute("""
    SELECT org_type, COUNT(*), SUM(estimated_members), ROUND(AVG(dues_rate_used)::numeric, 2)
    FROM form_990_estimates
    GROUP BY org_type
    ORDER BY SUM(estimated_members) DESC
""")
rows = cur.fetchall()

print()
print("=" * 70)
print("SUMMARY BY ORGANIZATION TYPE")
print("=" * 70)
for r in rows:
    print(f"  {r[0]:<20} {r[1]:>3} orgs  {r[2]:>10,} members  avg ${r[3]}/member")

# Grand total
cur.execute("SELECT COUNT(*), SUM(estimated_members), SUM(dues_revenue) FROM form_990_estimates")
total = cur.fetchone()
print("-" * 70)
print(f"  {'GRAND TOTAL':<20} {total[0]:>3} orgs  {total[1]:>10,} members  ${total[2]:,.0f} dues")

conn.close()
