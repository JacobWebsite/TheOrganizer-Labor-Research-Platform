"""
Find the 2,776 -- test different matching theories.
"""
import sys
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, '.')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()
p = lambda *a, **kw: print(*a, **kw, flush=True)

# Theory 5: employer_name appears as latest_union_name on another record
cur.execute("""
    SELECT COUNT(DISTINCT a.employer_id) FROM f7_employers_deduped a
    WHERE EXISTS (
        SELECT 1 FROM f7_employers_deduped b
        WHERE LOWER(TRIM(b.latest_union_name)) = LOWER(TRIM(a.employer_name))
        AND a.employer_id <> b.employer_id
    )
""")
p(f'Theory 5 (employer_name = latest_union_name of another): {cur.fetchone()[0]}')

# Theory 6: Check the F-7 raw data -- is there a view or original table?
cur.execute("""
    SELECT COUNT(DISTINCT employer_name) FROM f7_employers_deduped
    WHERE employer_name IN (SELECT DISTINCT latest_union_name FROM f7_employers_deduped WHERE latest_union_name IS NOT NULL)
""")
p(f'Theory 6 (employer_name IN set of all latest_union_names): {cur.fetchone()[0]}')

# Theory 6b: case-insensitive version
cur.execute("""
    SELECT COUNT(DISTINCT employer_id) FROM f7_employers_deduped
    WHERE LOWER(TRIM(employer_name)) IN (
        SELECT DISTINCT LOWER(TRIM(latest_union_name)) FROM f7_employers_deduped WHERE latest_union_name IS NOT NULL
    )
""")
p(f'Theory 6b (case-insensitive): {cur.fetchone()[0]}')

# Theory 7: Check union_file_number table -- maybe f7_union_employer_relations
# has the union filing as employer of itself
cur.execute("""
    SELECT COUNT(DISTINCT r.employer_id)
    FROM f7_union_employer_relations r
    JOIN unions_master u ON r.union_file_number::text = u.f_num
    JOIN f7_employers_deduped f ON r.employer_id = f.employer_id
    WHERE LOWER(TRIM(f.employer_name)) = LOWER(TRIM(u.union_name))
""")
p(f'Theory 7 (employer matched to its own union via relations): {cur.fetchone()[0]}')

# Theory 8: Maybe f7_union_name column on unions_master has more variants
# Let me also check employer_name against f7_employers table (non-deduped)
cur.execute("""SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'f7_employers'""")
p(f'f7_employers table exists: {cur.fetchone()[0] > 0}')

# Theory 9: Check the OLMS F-7 raw filings data
# employer filed a form where the employer is a union
cur.execute("""
    SELECT tablename FROM pg_tables
    WHERE schemaname = 'public' AND tablename LIKE 'f7%%'
    ORDER BY tablename
""")
p(f'F7 tables: {[r[0] for r in cur.fetchall()]}')

# Check f7_filings
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_filings' ORDER BY ordinal_position
""")
p(f'f7_filings columns: {[r[0] for r in cur.fetchall()]}')

conn.close()
