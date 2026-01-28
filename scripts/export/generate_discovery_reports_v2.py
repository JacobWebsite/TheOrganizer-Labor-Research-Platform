"""
Generate Discovery Reports - Updated with 2024 Expanded Data
Creates SQL insert statements, CSV export, and markdown report
"""

import psycopg2
from psycopg2.extras import RealDictCursor
import csv
from datetime import datetime
import os

DB_CONFIG = {
    'host': 'localhost',
    'port': 5432,
    'database': 'olms_multiyear',
    'user': 'postgres',
    'password': 'Juniordog33!'
}

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'output')

def get_connection():
    return psycopg2.connect(**DB_CONFIG)

def generate_sql_inserts(output_path):
    """Generate SQL INSERT statements"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute('''
        SELECT * FROM discovered_employers
        ORDER BY source_type, recognition_date
    ''')
    records = cur.fetchall()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"-- Union Discovery 2024 (All Sources) - Insert Statements\n")
        f.write(f"-- Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"-- Total Records: {len(records)}\n\n")

        for rec in records:
            # Escape single quotes
            employer = (rec['employer_name'] or '').replace("'", "''")
            employer_norm = (rec['employer_name_normalized'] or '').replace("'", "''")
            union_name = (rec['union_name'] or '').replace("'", "''")
            notes = (rec['notes'] or '').replace("'", "''")
            source_url = (rec['source_url'] or '').replace("'", "''")

            f.write(f"""INSERT INTO discovered_employers (
    employer_name, employer_name_normalized, city, state,
    union_name, affiliation, local_number, num_employees,
    recognition_type, recognition_date, naics_sector,
    source_url, source_type, notes, verification_status
) VALUES (
    '{employer}',
    '{employer_norm}',
    '{rec['city'] or ''}', '{rec['state'] or ''}',
    '{union_name}', '{rec['affiliation'] or ''}', {f"'{rec['local_number']}'" if rec['local_number'] else 'NULL'}, {rec['num_employees'] or 0},
    '{rec['recognition_type'] or ''}', {f"'{rec['recognition_date']}'" if rec['recognition_date'] else 'NULL'}, {f"'{rec['naics_sector']}'" if rec['naics_sector'] else 'NULL'},
    '{source_url}',
    '{rec['source_type'] or ''}',
    '{notes}',
    '{rec['verification_status'] or 'NEEDS_REVIEW'}'
);\n\n""")

    cur.close()
    conn.close()
    print(f"Generated: {output_path} ({len(records)} records)")

def generate_csv(output_path):
    """Generate CSV export"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute('''
        SELECT * FROM discovered_employers
        ORDER BY source_type, recognition_date
    ''')
    records = cur.fetchall()

    if records:
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=records[0].keys())
            writer.writeheader()
            writer.writerows(records)

    cur.close()
    conn.close()
    print(f"Generated: {output_path} ({len(records)} records)")

def generate_markdown_report(output_path):
    """Generate markdown report"""
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    # Get summary stats
    cur.execute('SELECT COUNT(*) as total, SUM(num_employees) as workers FROM discovered_employers')
    totals = cur.fetchone()

    cur.execute('''
        SELECT recognition_type, COUNT(*) as count, SUM(num_employees) as workers
        FROM discovered_employers
        GROUP BY recognition_type
        ORDER BY count DESC
    ''')
    by_type = cur.fetchall()

    cur.execute('''
        SELECT affiliation, COUNT(*) as count, SUM(num_employees) as workers
        FROM discovered_employers
        GROUP BY affiliation
        ORDER BY workers DESC NULLS LAST
    ''')
    by_affiliation = cur.fetchall()

    cur.execute('''
        SELECT source_type, COUNT(*) as count, SUM(num_employees) as workers
        FROM discovered_employers
        GROUP BY source_type
        ORDER BY count DESC
    ''')
    by_source = cur.fetchall()

    cur.execute('''
        SELECT employer_name, city, state, union_name, affiliation, num_employees, recognition_type, recognition_date, source_type
        FROM discovered_employers
        ORDER BY num_employees DESC
    ''')
    all_records = cur.fetchall()

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(f"# Union Discovery 2024 - Complete Report\n\n")
        f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
        f.write(f"## Overview\n\n")
        f.write(f"This report documents union organizing events discovered through systematic web research for 2024.\n\n")
        f.write(f"- **Total Events:** {totals['total']}\n")
        f.write(f"- **Total Workers Organized:** {totals['workers']:,}\n\n")

        f.write(f"## By Data Source\n\n")
        for row in by_source:
            workers = row['workers'] or 0
            f.write(f"- {row['source_type']}: {row['count']} events, {workers:,} workers\n")

        f.write(f"\n## By Recognition Type\n\n")
        for row in by_type:
            workers = row['workers'] or 0
            f.write(f"- {row['recognition_type']}: {row['count']} events ({workers:,} workers)\n")

        f.write(f"\n## By Union Affiliation\n\n")
        for row in by_affiliation:
            workers = row['workers'] or 0
            f.write(f"- {row['affiliation']}: {row['count']} events ({workers:,} workers)\n")

        f.write(f"\n## Complete List (Sorted by Worker Count)\n\n")
        f.write(f"| # | Employer | City, State | Union | Workers | Type | Date | Source |\n")
        f.write(f"|---|----------|-------------|-------|---------|------|------|--------|\n")

        for i, rec in enumerate(all_records, 1):
            employer = rec['employer_name'][:40]
            location = f"{rec['city'] or ''}, {rec['state'] or ''}"
            union = rec['affiliation'] or rec['union_name'][:20]
            workers = rec['num_employees'] or 0
            rec_type = rec['recognition_type'] or ''
            date = str(rec['recognition_date'])[:10] if rec['recognition_date'] else ''
            source = (rec['source_type'] or '').replace('DISCOVERY_2024', '2024').replace('_EXPANDED', '+')
            f.write(f"| {i} | {employer} | {location} | {union} | {workers:,} | {rec_type} | {date} | {source} |\n")

        # Notable events
        f.write(f"\n## Notable Events\n\n")

        # Largest
        f.write(f"### Largest Organizing Wins\n")
        for rec in all_records[:5]:
            f.write(f"- **{rec['employer_name']}** ({rec['state']}): {rec['num_employees']:,} workers - {rec['union_name']}\n")

        # By sector
        f.write(f"\n### Key Sectors\n")
        f.write(f"- **Automotive:** Volkswagen Chattanooga (4,300 workers) - UAW's historic Southern breakthrough\n")
        f.write(f"- **Video Games:** Activision + ZeniMax (1,061 workers) - CODE-CWA under Microsoft neutrality\n")
        f.write(f"- **Healthcare:** Sharp HealthCare (2,000 workers) - SEIU expansion in San Diego\n")
        f.write(f"- **Tech Retail:** Apple stores in MD & OK (178 workers) - First Apple retail contracts\n")
        f.write(f"- **Cannabis:** 3 dispensaries in MT, MO, MD - New industry organizing\n")

    cur.close()
    conn.close()
    print(f"Generated: {output_path}")

if __name__ == '__main__':
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    sql_path = os.path.join(OUTPUT_DIR, 'discovered_employers_all_2024.sql')
    csv_path = os.path.join(OUTPUT_DIR, 'discovered_employers_all_2024.csv')
    md_path = os.path.join(OUTPUT_DIR, 'discovery_2024_complete_report.md')

    print("Generating discovery reports...")
    print("=" * 60)
    generate_sql_inserts(sql_path)
    generate_csv(csv_path)
    generate_markdown_report(md_path)
    print("=" * 60)
    print("Done!")
