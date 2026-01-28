"""
Form 990 State Affiliate Data Loader
Loads extracted 990 data for state teacher affiliates
"""
import psycopg2

conn = psycopg2.connect(host='localhost', dbname='olms_multiyear', user='postgres', password='Juniordog33!')
cur = conn.cursor()

# State affiliates data from ProPublica
affiliates = [
    # CTA - California Teachers Association
    {
        'organization_name': 'California Teachers Association',
        'ein': '940362310',
        'state': 'CA',
        'city': 'Burlingame',
        'org_type': 'NEA_STATE',
        'tax_year': 2024,
        'tax_period_end': '2024-08-31',
        'dues_revenue': 217980320,
        'total_revenue': 238635993,
        'total_expenses': 213771683,
        'total_assets': 588311039,
        'net_assets': 511787670,
        'employee_count': 509,
        'published_members': 310000,
        'notes': 'Largest NEA state affiliate. CTA unified dues ~$737/member'
    },
    # NYSUT - New York State United Teachers (AFT/NEA dual affiliate)
    {
        'organization_name': 'New York State United Teachers',
        'ein': '141584772',
        'state': 'NY',
        'city': 'Latham',
        'org_type': 'AFT_NEA_STATE',
        'tax_year': 2024,
        'tax_period_end': '2024-08-31',
        'dues_revenue': 158123273,
        'total_revenue': 176756826,
        'total_expenses': 141857623,
        'total_assets': 308402111,
        'net_assets': -1204751,
        'employee_count': 466,
        'published_members': 700000,
        'notes': 'AFT/NEA dual affiliate. Includes UFT (140K NYC). Federation model.'
    },
]

for a in affiliates:
    if a.get('published_members') and a['dues_revenue']:
        rate = a['dues_revenue'] / a['published_members']
        estimated = int(a['dues_revenue'] / rate)
        
        insert_sql = """
        INSERT INTO form_990_estimates (
            organization_name, ein, state, city, org_type,
            tax_year, tax_period_end,
            dues_revenue, total_revenue, total_expenses, total_assets, net_assets,
            employee_count,
            dues_rate_used, dues_rate_source, estimated_members,
            confidence_level, cross_reference_source, cross_reference_value,
            notes
        ) VALUES (
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s,
            %s,
            %s, %s, %s,
            %s, %s, %s,
            %s
        )
        ON CONFLICT (ein, tax_year) DO UPDATE SET
            dues_revenue = EXCLUDED.dues_revenue,
            updated_at = CURRENT_TIMESTAMP
        """
        
        params = (
            a['organization_name'], a['ein'], a['state'], a['city'], a['org_type'],
            a['tax_year'], a['tax_period_end'],
            a['dues_revenue'], a['total_revenue'], a['total_expenses'], 
            a['total_assets'], a['net_assets'],
            a['employee_count'],
            round(rate, 2), f"Back-calculated from published membership ~{a['published_members']:,}",
            estimated,
            'HIGH', 'Published membership data', a['published_members'],
            a['notes']
        )
        
        cur.execute(insert_sql, params)
        print(f"Inserted: {a['organization_name']}")
        print(f"  Dues: ${a['dues_revenue']:,}")
        print(f"  Rate: ${rate:.2f}/member")
        print(f"  Est Members: {estimated:,}")
        print()

conn.commit()

# Show summary
cur.execute("""
    SELECT organization_name, state, dues_revenue, estimated_members, 
           dues_rate_used, confidence_level
    FROM form_990_estimates
    ORDER BY estimated_members DESC
""")
rows = cur.fetchall()

print("=" * 70)
print("FORM 990 ESTIMATES SUMMARY")
print("=" * 70)
for r in rows:
    name = r[0][:38] if r[0] else 'N/A'
    state = r[1] or 'N/A'
    members = r[3] or 0
    rate = r[4] or 0
    print(f"  {name:<40} {state:>5} {members:>10,} members @ ${rate:.2f}")

print()
total_members = sum(r[3] for r in rows if r[3])
print(f"Total estimated members: {total_members:,}")

conn.close()
