import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# Get total records per source
sources = ['990', 'sam', 'sec', 'whd', 'osha', 'bmf']
for src in sources:
    # This is tricky because we need the total count of the source table
    table_map = {
        '990': 'national_990_filers',
        'sam': 'sam_entities',
        'sec': 'sec_companies',
        'whd': 'whd_cases',
        'osha': 'osha_establishments',
        'bmf': 'irs_bmf'
    }
    table = table_map[src]
    cur.execute(f"SELECT COUNT(*) FROM {table}")
    total = cur.fetchone()[0]
    
    cur.execute(f"SELECT COUNT(DISTINCT source_id) FROM unified_match_log WHERE source_system = '{src}' AND status = 'active'")
    matched = cur.fetchone()[0]
    
    rate = 100.0 * matched / total if total > 0 else 0
    print(f"{src:4s}: {matched:>7,} / {total:>9,} ({rate:5.1f}%)")

cur.close()
conn.close()
