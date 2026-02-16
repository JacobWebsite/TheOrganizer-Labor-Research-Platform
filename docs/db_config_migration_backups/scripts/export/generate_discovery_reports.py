import os
"""Generate output files for Union Discovery 2024"""
import psycopg2
from psycopg2.extras import RealDictCursor
import csv
from datetime import datetime

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

cur.execute("SELECT * FROM discovered_employers WHERE source_type = 'DISCOVERY_2024' ORDER BY recognition_date")
rows = cur.fetchall()

# Generate SQL insert statements
with open('insert_statements_2024.sql', 'w', encoding='utf-8') as f:
    f.write('-- Union Discovery 2024 - Insert Statements\n')
    f.write(f'-- Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n')
    f.write(f'-- Total Records: {len(rows)}\n\n')

    for row in rows:
        local_num = f"'{row['local_number']}'" if row['local_number'] else 'NULL'
        notes = (row['notes'] or '').replace("'", "''")
        employer = row['employer_name'].replace("'", "''")
        union_name = row['union_name'].replace("'", "''")

        f.write(f"""INSERT INTO discovered_employers (
    employer_name, employer_name_normalized, city, state,
    union_name, affiliation, local_number, num_employees,
    recognition_type, recognition_date, naics_sector,
    source_url, source_type, notes, verification_status
) VALUES (
    '{employer}',
    '{row['employer_name_normalized']}',
    '{row['city']}', '{row['state']}',
    '{union_name}', '{row['affiliation']}', {local_num}, {row['num_employees']},
    '{row['recognition_type']}', '{row['recognition_date']}', '{row['naics_sector']}',
    '{row['source_url']}',
    'DISCOVERY_2024',
    '{notes}',
    '{row['verification_status']}'
);

""")

print(f'SQL file generated: insert_statements_2024.sql ({len(rows)} records)')

# Generate markdown report
with open('discovery_2024_report.md', 'w', encoding='utf-8') as f:
    f.write('# Union Discovery 2024 Report\n\n')
    f.write(f'**Generated:** {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n')
    f.write('## Overview\n\n')
    f.write('This report documents union organizing events discovered through systematic web research for 2024.\n\n')

    total_workers = sum(r['num_employees'] or 0 for r in rows)
    f.write(f'- **Total Events:** {len(rows)}\n')
    f.write(f'- **Total Workers Organized:** {total_workers:,}\n\n')

    # By type
    f.write('## By Recognition Type\n\n')
    types = {}
    for r in rows:
        t = r['recognition_type']
        types[t] = types.get(t, 0) + 1
    for t, c in sorted(types.items(), key=lambda x: -x[1]):
        f.write(f'- {t}: {c}\n')

    # By affiliation
    f.write('\n## By Union Affiliation\n\n')
    affs = {}
    for r in rows:
        a = r['affiliation']
        affs[a] = affs.get(a, 0) + 1
    for a, c in sorted(affs.items(), key=lambda x: -x[1]):
        f.write(f'- {a}: {c}\n')

    # Full list
    f.write('\n## Complete List\n\n')
    f.write('| # | Employer | City, State | Union | Workers | Type | Date |\n')
    f.write('|---|----------|-------------|-------|---------|------|------|\n')
    for i, r in enumerate(rows, 1):
        emp_name = r['employer_name'][:35]
        f.write(f"| {i} | {emp_name} | {r['city']}, {r['state']} | {r['affiliation']} | {r['num_employees']:,} | {r['recognition_type']} | {r['recognition_date']} |\n")

    # Notable events
    f.write('\n## Notable Events\n\n')
    largest = max(rows, key=lambda x: x['num_employees'] or 0)
    f.write(f'### Largest: {largest["employer_name"]}\n')
    f.write(f'- **Workers:** {largest["num_employees"]:,}\n')
    f.write(f'- **Union:** {largest["union_name"]}\n')
    f.write(f'- **Notes:** {largest["notes"]}\n\n')

    f.write('### First-of-Kind Organizing\n')
    firsts = [r for r in rows if 'First' in (r['notes'] or '')]
    for r in firsts:
        f.write(f'- **{r["employer_name"]}**: {r["notes"]}\n')

print(f'Report generated: discovery_2024_report.md')

conn.close()
