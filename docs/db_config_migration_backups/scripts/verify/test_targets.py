"""Test organizing targets data directly."""
import psycopg2
from psycopg2.extras import RealDictCursor
import os

DB_CONFIG = {
    'host': os.environ.get('DB_HOST', 'localhost'),
    'port': int(os.environ.get('DB_PORT', '5432')),
    'database': os.environ.get('DB_NAME', 'olms_multiyear'),
    'user': os.environ.get('DB_USER', 'postgres'),
    'password': os.environ.get('DB_PASSWORD', ''),
}

conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
cur = conn.cursor()

# Test the query from the API
cur.execute('''
    SELECT
        COUNT(*) as total_targets,
        COUNT(*) FILTER (WHERE has_existing_afscme_contract = FALSE) as unorganized,
        COUNT(*) FILTER (WHERE priority_tier = 'TOP') as top_tier,
        COUNT(*) FILTER (WHERE priority_tier = 'HIGH') as high_tier,
        COUNT(*) FILTER (WHERE priority_tier = 'MEDIUM') as medium_tier,
        SUM(total_govt_funding) as total_funding,
        SUM(employee_count) as total_employees,
        AVG(priority_score) as avg_score
    FROM organizing_targets
''')
overall = cur.fetchone()

print('=== Organizing Targets Stats ===')
print(f'Total targets: {overall["total_targets"]}')
print(f'Unorganized: {overall["unorganized"]}')
print(f'TOP tier: {overall["top_tier"]}')
print(f'HIGH tier: {overall["high_tier"]}')
print(f'MEDIUM tier: {overall["medium_tier"]}')
print(f'Total funding: ${float(overall["total_funding"] or 0)/1e9:.2f}B')
print(f'Avg score: {float(overall["avg_score"] or 0):.1f}')

# Top targets
cur.execute('''
    SELECT employer_name, city, industry_category, priority_tier,
           total_govt_funding, employee_count, priority_score
    FROM organizing_targets
    WHERE priority_tier = 'TOP'
    ORDER BY priority_score DESC
    LIMIT 10
''')
print('\n=== Top 10 TOP-Tier Targets ===')
for t in cur.fetchall():
    funding = float(t['total_govt_funding'] or 0)
    print(f'{t["employer_name"][:45]} | {t["city"]} | ${funding/1e6:.1f}M | Score: {t["priority_score"]}')

cur.close()
conn.close()
print('\nTest completed!')
