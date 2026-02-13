import sys
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

# 1. Find all OSHA-related tables
print('=' * 80)
print('OSHA-RELATED TABLES')
print('=' * 80)
cur.execute("""
    SELECT table_name 
    FROM information_schema.tables 
    WHERE table_name LIKE '%%osha%%' 
    ORDER BY table_name
""")
osha_tables = [row[0] for row in cur.fetchall()]
for t in osha_tables:
    print(f'  {t}')
print()

# 2. Row counts for each table
print('=' * 80)
print('ROW COUNTS')
print('=' * 80)
for t in osha_tables:
    cur.execute(f'SELECT COUNT(*) FROM "{t}"')
    count = cur.fetchone()[0]
    print(f'  {t}: {count:,} rows')
print()

# 3. Column info for each table
print('=' * 80)
print('COLUMN DETAILS PER TABLE')
print('=' * 80)
for t in osha_tables:
    print()
    print(f'--- {t} ---')
    cur.execute("""
        SELECT column_name, data_type, character_maximum_length, is_nullable
        FROM information_schema.columns
        WHERE table_name = %s
        ORDER BY ordinal_position
    """, (t,))
    cols = cur.fetchall()
    hdr = f'{"Column":<40} {"Type":<25} {"MaxLen":<8} {"Nullable"}'
    print(f'  {hdr}')
    print(f'  {"-"*40} {"-"*25} {"-"*8} {"-"*8}')
    for col_name, dtype, maxlen, nullable in cols:
        ml = str(maxlen) if maxlen else ''
        print(f'  {col_name:<40} {dtype:<25} {ml:<8} {nullable}')
print()

# 4. Foreign keys involving OSHA tables
print('=' * 80)
print('FOREIGN KEYS INVOLVING OSHA TABLES')
print('=' * 80)
cur.execute("""
    SELECT
        tc.table_name AS source_table,
        kcu.column_name AS source_column,
        ccu.table_name AS target_table,
        ccu.column_name AS target_column,
        tc.constraint_name
    FROM information_schema.table_constraints tc
    JOIN information_schema.key_column_usage kcu
        ON tc.constraint_name = kcu.constraint_name
    JOIN information_schema.constraint_column_usage ccu
        ON tc.constraint_name = ccu.constraint_name
    WHERE tc.constraint_type = 'FOREIGN KEY'
      AND (tc.table_name LIKE '%%osha%%' OR ccu.table_name LIKE '%%osha%%')
    ORDER BY tc.table_name
""")
fks = cur.fetchall()
if fks:
    for src_tbl, src_col, tgt_tbl, tgt_col, cname in fks:
        print(f'  {src_tbl}.{src_col} -> {tgt_tbl}.{tgt_col}  ({cname})')
else:
    print('  (No foreign keys found)')
print()

# 4b. Check for common columns across OSHA tables
print('=' * 80)
print('COMMON COLUMNS ACROSS OSHA TABLES (potential join keys)')
print('=' * 80)
all_cols = {}
for t in osha_tables:
    cur.execute("""
        SELECT column_name FROM information_schema.columns
        WHERE table_name = %s ORDER BY ordinal_position
    """, (t,))
    all_cols[t] = set(row[0] for row in cur.fetchall())

if len(osha_tables) >= 2:
    from collections import Counter
    col_counter = Counter()
    for t, cols_set in all_cols.items():
        for c in cols_set:
            col_counter[c] += 1
    shared = {c: cnt for c, cnt in col_counter.items() if cnt >= 2}
    for col_name, cnt in sorted(shared.items(), key=lambda x: -x[1]):
        tables_with = [t for t in osha_tables if col_name in all_cols[t]]
        print(f'  {col_name} (in {cnt} tables): {", ".join(tables_with)}')
else:
    print('  Only one OSHA table found.')
print()

# 5. Sample rows from each table
print('=' * 80)
print('SAMPLE ROWS (LIMIT 3)')
print('=' * 80)
for t in osha_tables:
    print()
    print(f'--- {t} (first 3 rows) ---')
    cur.execute(f'SELECT * FROM "{t}" LIMIT 3')
    rows = cur.fetchall()
    col_names = [desc[0] for desc in cur.description]
    for i, row in enumerate(rows):
        print(f'  Row {i+1}:')
        for cn, val in zip(col_names, row):
            print(f'    {cn}: {val}')
        print()

# 6. Check indexes on OSHA tables
print('=' * 80)
print('INDEXES ON OSHA TABLES')
print('=' * 80)
for t in osha_tables:
    cur.execute("""
        SELECT indexname, indexdef
        FROM pg_indexes
        WHERE tablename = %s
        ORDER BY indexname
    """, (t,))
    idxs = cur.fetchall()
    if idxs:
        print()
        print(f'  {t}:')
        for iname, idef in idxs:
            print(f'    {iname}: {idef}')
    else:
        print()
        print(f'  {t}: (no indexes)')

cur.close()
conn.close()
print()
print('Done.')
