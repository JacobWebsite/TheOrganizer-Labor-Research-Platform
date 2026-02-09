import os
"""Update views to use new naics_detailed column"""
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

# Update the view to use naics_detailed
print('=== Updating v_employer_industry_outlook View ===')

# Drop and recreate to allow column changes
cur.execute('DROP VIEW IF EXISTS v_employer_industry_outlook CASCADE')
conn.commit()

cur.execute('''
    CREATE VIEW v_employer_industry_outlook AS
    SELECT
        e.employer_id,
        e.employer_name,
        e.city,
        e.state,
        e.naics AS employer_naics,
        e.naics_detailed,
        e.naics_source,
        e.naics_confidence,
        e.latest_unit_size AS workers,
        e.latest_union_name AS union_name,
        p.matrix_code,
        p.industry_title,
        p.employment_2024,
        p.employment_2034,
        p.employment_change_pct AS industry_growth_pct,
        p.growth_category AS industry_outlook
    FROM f7_employers_deduped e
    JOIN bls_industry_projections p
        ON LEFT(p.matrix_code, 2) = COALESCE(LEFT(e.naics_detailed, 2), e.naics)
        AND p.matrix_code LIKE '%0000'
    WHERE COALESCE(e.naics_detailed, e.naics) IS NOT NULL
''')
conn.commit()
print('  Updated v_employer_industry_outlook with naics_detailed support')

# Also create a new view for detailed NAICS info
print('Creating v_employer_naics_enhanced View')
cur.execute('''
    CREATE OR REPLACE VIEW v_employer_naics_enhanced AS
    SELECT
        e.employer_id,
        e.employer_name,
        e.city,
        e.state,
        e.naics AS original_naics,
        e.naics_detailed,
        e.naics_source,
        e.naics_confidence,
        e.latest_unit_size AS workers,
        e.latest_union_name AS union_name,
        p_sector.industry_title AS sector_name,
        p_sector.growth_category AS sector_outlook,
        p_sector.employment_change_pct AS sector_growth_pct,
        p_detail.matrix_code AS detail_matrix_code,
        p_detail.industry_title AS detail_industry_name,
        p_detail.growth_category AS detail_outlook,
        p_detail.employment_change_pct AS detail_growth_pct
    FROM f7_employers_deduped e
    LEFT JOIN bls_industry_projections p_sector
        ON LEFT(COALESCE(e.naics_detailed, e.naics), 2) || '0000' = p_sector.matrix_code
    LEFT JOIN bls_industry_projections p_detail
        ON e.naics_detailed = p_detail.matrix_code
        AND e.naics_source = 'OSHA'
''')
conn.commit()
print('  Created v_employer_naics_enhanced view')

# Test the updated view
print('\n=== Testing Updated View ===')
cur.execute('''
    SELECT employer_name, employer_naics, naics_detailed, naics_source, industry_outlook
    FROM v_employer_industry_outlook
    WHERE naics_source = 'OSHA'
    ORDER BY workers DESC NULLS LAST
    LIMIT 5
''')
for row in cur.fetchall():
    print(f'  {row[0][:35]}: {row[1]} -> {row[2]} ({row[3]}) - {row[4]}')

conn.close()
print('\nDone!')
