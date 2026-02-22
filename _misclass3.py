"""
Find the 2,776 -- more theories.
"""
import sys
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, '.')
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()
p = lambda *a, **kw: print(*a, **kw, flush=True)

# Check f7_employers (non-deduped)
cur.execute("SELECT COUNT(*) FROM f7_employers")
p(f'f7_employers (non-deduped) count: {cur.fetchone()[0]}')

cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers' ORDER BY ordinal_position
""")
p(f'f7_employers columns: {[r[0] for r in cur.fetchall()]}')

# Theory 10: employer matches the latest_union_name on that SAME record
# (not another record, but its own)
cur.execute("""
    SELECT COUNT(*) FROM f7_employers_deduped
    WHERE LOWER(TRIM(employer_name)) = LOWER(TRIM(latest_union_name))
""")
p(f'Theory 10 (employer = own latest_union_name): {cur.fetchone()[0]}')

# Theory 11: Maybe the audit checked f7_employers (pre-dedup)?
cur.execute("""
    SELECT COUNT(DISTINCT employer_name) FROM f7_employers
    WHERE LOWER(TRIM(employer_name)) IN (
        SELECT DISTINCT LOWER(TRIM(latest_union_name)) FROM f7_employers WHERE latest_union_name IS NOT NULL
    )
""")
p(f'Theory 11 (f7_employers pre-dedup, employer IN union_names): {cur.fetchone()[0]}')

# Theory 12: Maybe it's employer_name matching against NLRB data or LM filing names
# Check if nlrb_participants has labor org names
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id) FROM f7_employers_deduped f
    WHERE EXISTS (
        SELECT 1 FROM nlrb_participants np
        WHERE np.participant_type = 'Labor Organization'
        AND LOWER(TRIM(np.participant_name)) = LOWER(TRIM(f.employer_name))
    )
""")
p(f'Theory 12 (employer = NLRB labor org participant): {cur.fetchone()[0]}')

# Theory 13: Maybe it was matching against all LM-reported union names across all years
cur.execute("SELECT COUNT(DISTINCT LOWER(TRIM(union_name))) FROM lm_data")
p(f'Distinct lm_data union names (lower/trim): {cur.fetchone()[0]}')

cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id)
    FROM f7_employers_deduped f
    WHERE LOWER(TRIM(f.employer_name)) IN (
        SELECT DISTINCT LOWER(TRIM(union_name)) FROM lm_data WHERE union_name IS NOT NULL
    )
""")
p(f'Theory 13 (employer = lm_data union_name, all years): {cur.fetchone()[0]}')

# Theory 14: What about the LM filing employer field?
# Maybe LM data has an employer_name column too?
cur.execute("""
    SELECT column_name FROM information_schema.columns
    WHERE table_name = 'lm_data' AND column_name ILIKE '%%employer%%'
""")
p(f'lm_data employer columns: {[r[0] for r in cur.fetchall()]}')

# Theory 15: Maybe it's the F-7 raw data - what does f7_employers have?
cur.execute("""
    SELECT DISTINCT LOWER(TRIM(employer_name))
    FROM f7_employers
    WHERE employer_name ILIKE '%%local%%' OR employer_name ILIKE '%%union%%'
    LIMIT 10
""")
p(f'Sample f7_employers with union keywords: {[r[0] for r in cur.fetchall()]}')

# Theory 16: Maybe the audit used a larger set of union names
# from combining multiple sources
# Let's just count how many employers have union-like names using a comprehensive keyword list
cur.execute("""
    SELECT COUNT(*) FROM f7_employers_deduped
    WHERE employer_name ~* '\\m(local|union|brotherhood|federation|council|association of|laborers|teamsters|carpenters|electricians|plumbers|ironworkers|steelworkers|machinists|nurses|teachers|firefighters|afscme|seiu|ufcw|ibew|iam|iatse|unite here|cwa|uaw|usw|afge|afl.cio|ibt|apwu|nalc|nrlca|opeiu|liuna|painters|pipefitters|boilermakers|bricklayers|operating engineers|sheet metal|elevator constructors|roofers|asbestos|glaziers|sprinkler|tile|plasterers|lathers|cement masons|marble polishers|district council|joint board|organizing committee|staff union|employees union|workers union|international union|national union)\\M'
""")
p(f'Theory 16 (comprehensive regex): {cur.fetchone()[0]}')

# The original session likely created the audit inline -- run with the broader approach
# Let's also check: employer_name that appears as a union_name in f7_union_employer_relations context
cur.execute("""
    SELECT COUNT(DISTINCT f.employer_id)
    FROM f7_employers_deduped f
    JOIN f7_union_employer_relations r ON f.employer_id = r.employer_id
    WHERE LOWER(TRIM(f.employer_name)) = LOWER(TRIM(f.latest_union_name))
""")
p(f'Self-ref + has f7 relation: {cur.fetchone()[0]}')

# Theory 17: Maybe the 2,776 was computed by: for each employer, check if
# employer_name is a substring of (or fuzzy-matches) any union name.
# Or simply: how many employers have names matching a broad union regex
# AND also have latest_union_fnum pointing to themselves?
# Let me just count how many employers have their employer_id matching a union f_num
cur.execute("""
    SELECT COUNT(*) FROM f7_employers_deduped f
    WHERE EXISTS (SELECT 1 FROM unions_master u WHERE u.f_num = f.employer_id)
""")
p(f'Theory 17 (employer_id = some union f_num): {cur.fetchone()[0]}')

# The number is 2,776 and the description says "Exact name cross-matches (employer = union)"
# Maybe the audit checked employer_name against ALL union names across ALL tables
# Let's build the comprehensive union name set
p('\n--- Building comprehensive union name set ---')
cur.execute("SELECT DISTINCT LOWER(TRIM(union_name)) FROM unions_master WHERE union_name IS NOT NULL")
all_union_names = set(r[0] for r in cur.fetchall())
p(f'  unions_master.union_name: {len(all_union_names)}')

cur.execute("SELECT DISTINCT LOWER(TRIM(f7_union_name)) FROM unions_master WHERE f7_union_name IS NOT NULL")
f7_names = set(r[0] for r in cur.fetchall())
all_union_names |= f7_names
p(f'  + unions_master.f7_union_name: {len(f7_names)} -> total {len(all_union_names)}')

cur.execute("SELECT DISTINCT LOWER(TRIM(union_name)) FROM lm_data WHERE union_name IS NOT NULL")
lm_names = set(r[0] for r in cur.fetchall())
all_union_names |= lm_names
p(f'  + lm_data.union_name: {len(lm_names)} -> total {len(all_union_names)}')

cur.execute("SELECT DISTINCT LOWER(TRIM(latest_union_name)) FROM f7_employers_deduped WHERE latest_union_name IS NOT NULL")
f7e_names = set(r[0] for r in cur.fetchall())
all_union_names |= f7e_names
p(f'  + f7_employers_deduped.latest_union_name: {len(f7e_names)} -> total {len(all_union_names)}')

# Now check matches
cur.execute("SELECT employer_id, LOWER(TRIM(employer_name)) AS n FROM f7_employers_deduped")
matches = []
for r in cur.fetchall():
    if r[1] in all_union_names:
        matches.append(r[0])
p(f'\nEmployer names matching comprehensive union name set: {len(matches)}')

# That's probably still not 2,776. Let me try the nlrb_participants approach
cur.execute("SELECT DISTINCT LOWER(TRIM(participant_name)) FROM nlrb_participants WHERE participant_type ILIKE '%%Labor%%'")
nlrb_names = set(r[0] for r in cur.fetchall())
all_union_names |= nlrb_names
p(f'  + nlrb labor org names: {len(nlrb_names)} -> total {len(all_union_names)}')

matches2 = []
cur.execute("SELECT employer_id, LOWER(TRIM(employer_name)) AS n FROM f7_employers_deduped")
for r in cur.fetchall():
    if r[1] in all_union_names:
        matches2.append(r[0])
p(f'Employer names matching ALL sources: {len(matches2)}')

conn.close()
