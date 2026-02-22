"""
Misclassification Research: Analyze employer records that are likely labor orgs.
Read-only -- no data modifications.
Uses Python-side name matching to avoid slow SQL cross-joins.
"""
import sys, os
sys.stdout.reconfigure(line_buffering=True)
sys.path.insert(0, '.')
from db_config import get_connection
from psycopg2.extras import RealDictCursor

conn = get_connection()
cur = conn.cursor(cursor_factory=RealDictCursor)

SEP = '=' * 80
p = lambda *a, **kw: print(*a, **kw, flush=True)

# ── Step 1: Load union names into a Python set ──────────────────────────────
p("Loading union names from unions_master...")
cur.execute("SELECT DISTINCT LOWER(TRIM(union_name)) AS n FROM unions_master WHERE union_name IS NOT NULL")
union_names = set(r['n'] for r in cur.fetchall())
cur.execute("SELECT DISTINCT LOWER(TRIM(f7_union_name)) AS n FROM unions_master WHERE f7_union_name IS NOT NULL")
union_names |= set(r['n'] for r in cur.fetchall())
p(f"  {len(union_names):,} distinct union names loaded")

# ── Step 2: Find matching employer_ids ──────────────────────────────────────
p("Scanning f7_employers_deduped for matches...")
cur.execute("SELECT employer_id, LOWER(TRIM(employer_name)) AS n FROM f7_employers_deduped")
candidate_ids = []
for r in cur.fetchall():
    if r['n'] in union_names:
        candidate_ids.append(r['employer_id'])
p(f"  {len(candidate_ids):,} employer records match a union name")

# ── Step 3: Create temp table from IDs ──────────────────────────────────────
p("Creating temp table from matched IDs...")
cur.execute("CREATE TEMP TABLE _cand_ids (employer_id TEXT PRIMARY KEY)")
from psycopg2.extras import execute_values
execute_values(cur, "INSERT INTO _cand_ids (employer_id) VALUES %s", [(i,) for i in candidate_ids], page_size=1000)
p(f"  Inserted {len(candidate_ids):,} IDs")

# Build the full temp table
cur.execute("""
    CREATE TEMP TABLE _cand AS
    SELECT f.employer_id, f.employer_name, f.city, f.state,
           f.latest_unit_size, f.latest_union_fnum, f.latest_union_name,
           f.is_historical, f.naics, f.filing_count, f.data_quality_flag, f.exclude_reason
    FROM f7_employers_deduped f
    JOIN _cand_ids ci ON f.employer_id = ci.employer_id
""")
cur.execute("CREATE INDEX ON _cand(employer_id)")
p("Temp table built with index.\n")

# ── Add helper columns ──────────────────────────────────────────────────────
p("Adding helper columns...")

cur.execute("ALTER TABLE _cand ADD COLUMN has_f7 BOOLEAN DEFAULT FALSE")
cur.execute("""UPDATE _cand c SET has_f7 = TRUE
    WHERE EXISTS (SELECT 1 FROM f7_union_employer_relations r WHERE r.f7_employer_id = c.employer_id)""")
p(f"  has_f7: {cur.rowcount} updated")

cur.execute("ALTER TABLE _cand ADD COLUMN n_unions INT DEFAULT 0")
cur.execute("""UPDATE _cand c SET n_unions = sub.cnt
    FROM (SELECT f7_employer_id, COUNT(DISTINCT union_fnum) AS cnt FROM f7_union_employer_relations GROUP BY 1) sub
    WHERE c.employer_id = sub.f7_employer_id""")
p(f"  n_unions: {cur.rowcount} updated")

cur.execute("ALTER TABLE _cand ADD COLUMN has_uml BOOLEAN DEFAULT FALSE, ADD COLUMN uml_cnt INT DEFAULT 0")
cur.execute("""UPDATE _cand c SET has_uml = TRUE, uml_cnt = sub.cnt
    FROM (SELECT target_id, COUNT(*) AS cnt FROM unified_match_log WHERE status = 'active' GROUP BY 1) sub
    WHERE c.employer_id = sub.target_id""")
p(f"  has_uml: {cur.rowcount} updated")

cur.execute("ALTER TABLE _cand ADD COLUMN self_ref BOOLEAN DEFAULT FALSE")
cur.execute("""UPDATE _cand SET self_ref = TRUE
    WHERE LOWER(TRIM(employer_name)) = LOWER(TRIM(COALESCE(latest_union_name, '')))""")
p(f"  self_ref: {cur.rowcount} updated")
p("")

# ══════════════════════════════════════════════════════════════════════════════
p(SEP)
p('QUERY A: REPRODUCE THE ORIGINAL AUDIT')
p(SEP)

cur.execute("""
    SELECT COUNT(*) AS cnt FROM f7_employers_deduped
    WHERE employer_name ILIKE '%%local %%' OR employer_name ILIKE '%%union%%'
       OR employer_name ILIKE '%%brotherhood%%' OR employer_name ILIKE '%%federation%%'
       OR employer_name ILIKE '%%laborers%%' OR employer_name ILIKE '%%teamsters%%'
       OR employer_name ILIKE '%%carpenters%%' OR employer_name ILIKE '%%electricians%%'
       OR employer_name ILIKE '%%plumbers%%' OR employer_name ILIKE '%%ironworkers%%'
       OR employer_name ILIKE '%%steelworkers%%' OR employer_name ILIKE '%%afscme%%'
       OR employer_name ILIKE '%%seiu%%' OR employer_name ILIKE '%%ufcw%%'
       OR employer_name ILIKE '%%ibew%%' OR employer_name ILIKE '%%iatse%%'
       OR employer_name ILIKE '%%unite here%%' OR employer_name ILIKE '%%cwa %%'
       OR employer_name ILIKE '%%uaw %%' OR employer_name ILIKE '%%afge%%'
       OR employer_name ILIKE '%%afl-cio%%'
""")
p(f"A1 - Employer names matching union keywords: {cur.fetchone()['cnt']:,}")
p(f"A2 - Exact name cross-matches (employer=union): {len(candidate_ids):,}")

cur.execute("""
    SELECT flag_type, COUNT(*) AS cnt FROM employer_review_flags
    WHERE flag_type IN ('LABOR_ORG_NOT_EMPLOYER', 'ALREADY_UNION') GROUP BY flag_type
""")
p("A3 - Already flagged:")
for row in cur.fetchall():
    p(f"  {row['flag_type']}: {row['cnt']}")

cur.execute("""
    SELECT f.source_id, f.flag_type, f.notes, e.employer_name
    FROM employer_review_flags f LEFT JOIN f7_employers_deduped e ON e.employer_id = f.source_id
    WHERE f.flag_type IN ('LABOR_ORG_NOT_EMPLOYER', 'ALREADY_UNION')
""")
for row in cur.fetchall():
    p(f"  [{row['flag_type']}] {row['source_id']}: {row['employer_name'] or 'N/A'} -- {row['notes'] or ''}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY B: CANDIDATES WITH F-7 UNION-EMPLOYER RELATIONS')
p(SEP)

cur.execute("""SELECT COUNT(*) AS total, COUNT(CASE WHEN has_f7 THEN 1 END) AS yes,
    COUNT(CASE WHEN NOT has_f7 THEN 1 END) AS no FROM _cand""")
row = cur.fetchone()
p(f"Total:       {row['total']:,}")
p(f"Have F-7:    {row['yes']:,}")
p(f"No F-7:      {row['no']:,}")

cur.execute("""SELECT employer_name, state, latest_unit_size, n_unions
    FROM _cand WHERE has_f7 ORDER BY n_unions DESC LIMIT 15""")
p("\nTop 15 by distinct union count:")
p(f"  {'Employer':<55} {'St':>2} {'Workers':>8} {'#U':>4}")
p(f"  {'-'*72}")
for r in cur.fetchall():
    p(f"  {r['employer_name'][:55]:<55} {r['state'] or '':>2} {r['latest_unit_size'] or 0:>8,} {r['n_unions']:>4}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY C: CANDIDATES WITH UML MATCHES')
p(SEP)

cur.execute("""SELECT COUNT(*) AS total, COUNT(CASE WHEN has_uml THEN 1 END) AS yes,
    COUNT(CASE WHEN NOT has_uml THEN 1 END) AS no FROM _cand""")
row = cur.fetchone()
p(f"Total:          {row['total']:,}")
p(f"Have UML:       {row['yes']:,}")
p(f"No UML:         {row['no']:,}")

cur.execute("""SELECT u.source_system, COUNT(DISTINCT c.employer_id) AS emps, COUNT(*) AS matches
    FROM _cand c JOIN unified_match_log u ON c.employer_id = u.target_id AND u.status = 'active'
    GROUP BY u.source_system ORDER BY emps DESC""")
p("\nBy source system:")
p(f"  {'Source':<15} {'Employers':>10} {'Matches':>10}")
p(f"  {'-'*38}")
for r in cur.fetchall():
    p(f"  {r['source_system']:<15} {r['emps']:>10,} {r['matches']:>10,}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY D: CANDIDATES IN UNIFIED SCORECARD')
p(SEP)

cur.execute("""SELECT COUNT(*) AS total, COUNT(s.f7_employer_id) AS in_sc,
    COUNT(CASE WHEN s.score_osha IS NOT NULL THEN 1 END) AS osha,
    COUNT(CASE WHEN s.score_nlrb IS NOT NULL THEN 1 END) AS nlrb,
    COUNT(CASE WHEN s.score_whd IS NOT NULL THEN 1 END) AS whd,
    COUNT(CASE WHEN s.score_contracts IS NOT NULL THEN 1 END) AS contracts,
    COUNT(CASE WHEN s.score_financial IS NOT NULL THEN 1 END) AS fin,
    COUNT(CASE WHEN s.score_size IS NOT NULL THEN 1 END) AS sz,
    ROUND(AVG(s.unified_score)::numeric, 2) AS avg_sc,
    ROUND(AVG(s.coverage_pct)::numeric, 1) AS avg_cov
    FROM _cand c LEFT JOIN mv_unified_scorecard s ON c.employer_id = s.f7_employer_id""")
row = cur.fetchone()
p(f"Total:            {row['total']:,}")
p(f"In scorecard:     {row['in_sc']:,}")
p(f"  has_osha:       {row['osha']:,}")
p(f"  has_nlrb:       {row['nlrb']:,}")
p(f"  has_whd:        {row['whd']:,}")
p(f"  has_contracts:  {row['contracts']:,}")
p(f"  has_financial:  {row['fin']:,}")
p(f"  has_size:       {row['sz']:,}")
p(f"  avg score:      {row['avg_sc']}")
p(f"  avg coverage:   {row['avg_cov']}%%")

cur.execute("""SELECT s.score_tier, COUNT(*) AS cnt
    FROM _cand c JOIN mv_unified_scorecard s ON c.employer_id = s.f7_employer_id
    GROUP BY s.score_tier ORDER BY cnt DESC""")
p("\nScore tiers:")
for r in cur.fetchall():
    p(f"  {r['score_tier'] or 'NULL':<10}: {r['cnt']:,}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY E: SAMPLE EMPLOYER NAMES')
p(SEP)

cur.execute("""SELECT employer_name, city, state, latest_unit_size, latest_union_name, uml_cnt
    FROM _cand WHERE has_uml ORDER BY latest_unit_size DESC NULLS LAST LIMIT 15""")
p("\n-- WITH UML matches (potentially legitimate employers) --")
p(f"  {'Employer':<48} {'City':<14} {'St':>2} {'Wkrs':>7} {'UML':>4} {'Union':<25}")
p(f"  {'-'*105}")
for r in cur.fetchall():
    p(f"  {r['employer_name'][:48]:<48} {(r['city'] or '')[:14]:<14} {r['state'] or '':>2} {r['latest_unit_size'] or 0:>7,} {r['uml_cnt']:>4} {(r['latest_union_name'] or '')[:25]:<25}")

cur.execute("""SELECT employer_name, city, state, latest_unit_size, latest_union_name
    FROM _cand WHERE NOT has_uml ORDER BY latest_unit_size DESC NULLS LAST LIMIT 15""")
p("\n-- WITHOUT UML matches (likely truly misclassified) --")
p(f"  {'Employer':<55} {'City':<14} {'St':>2} {'Wkrs':>7} {'Union':<25}")
p(f"  {'-'*108}")
for r in cur.fetchall():
    p(f"  {r['employer_name'][:55]:<55} {(r['city'] or '')[:14]:<14} {r['state'] or '':>2} {r['latest_unit_size'] or 0:>7,} {(r['latest_union_name'] or '')[:25]:<25}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY F: latest_unit_size DISTRIBUTION')
p(SEP)

cur.execute("""SELECT COUNT(*) AS total,
    COUNT(CASE WHEN latest_unit_size > 0 THEN 1 END) AS yes,
    COUNT(CASE WHEN COALESCE(latest_unit_size, 0) = 0 THEN 1 END) AS no,
    SUM(COALESCE(latest_unit_size, 0)) AS tw,
    ROUND(AVG(CASE WHEN latest_unit_size > 0 THEN latest_unit_size END)::numeric, 1) AS avg_w,
    MAX(latest_unit_size) AS mx FROM _cand""")
row = cur.fetchone()
p(f"Total:            {row['total']:,}")
p(f"Has workers > 0:  {row['yes']:,}")
p(f"No workers:       {row['no']:,}")
p(f"Total workers:    {row['tw']:,}")
p(f"Avg (when > 0):   {row['avg_w']}")
p(f"Max:              {row['mx']:,}" if row['mx'] else "Max: N/A")

cur.execute("""SELECT CASE
    WHEN COALESCE(latest_unit_size, 0) = 0 THEN '0_none'
    WHEN latest_unit_size BETWEEN 1 AND 10 THEN '1-10'
    WHEN latest_unit_size BETWEEN 11 AND 50 THEN '11-50'
    WHEN latest_unit_size BETWEEN 51 AND 100 THEN '51-100'
    WHEN latest_unit_size BETWEEN 101 AND 500 THEN '101-500'
    WHEN latest_unit_size BETWEEN 501 AND 1000 THEN '501-1000'
    WHEN latest_unit_size > 1000 THEN '1001+'
    END AS bucket, COUNT(*) AS cnt, SUM(COALESCE(latest_unit_size, 0)) AS w
    FROM _cand GROUP BY 1 ORDER BY MIN(COALESCE(latest_unit_size, 0))""")
p("\nSize buckets:")
p(f"  {'Bucket':<12} {'Count':>8} {'Workers':>12}")
p(f"  {'-'*35}")
for r in cur.fetchall():
    p(f"  {r['bucket']:<12} {r['cnt']:>8,} {r['w']:>12,}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY G: OVERLAP WITH unions_master')
p(SEP)

cur.execute("""SELECT COUNT(*) AS cnt FROM _cand c
    WHERE EXISTS (SELECT 1 FROM unions_master u WHERE u.f_num = c.employer_id)""")
p(f"employer_id is also a union f_num: {cur.fetchone()['cnt']:,}")

cur.execute("""SELECT COUNT(*) AS total,
    COUNT(CASE WHEN self_ref THEN 1 END) AS sr,
    COUNT(CASE WHEN latest_union_name IS NULL THEN 1 END) AS nu,
    COUNT(CASE WHEN NOT self_ref AND latest_union_name IS NOT NULL THEN 1 END) AS du
    FROM _cand""")
row = cur.fetchone()
p(f"\nEmployer name vs representing union:")
p(f"  Total:                     {row['total']:,}")
p(f"  Self-ref (name=union):     {row['sr']:,}")
p(f"  Different union:           {row['du']:,}")
p(f"  No union name:             {row['nu']:,}")

cur.execute("""SELECT employer_name, employer_id, latest_union_fnum, latest_unit_size, state
    FROM _cand WHERE self_ref ORDER BY latest_unit_size DESC NULLS LAST LIMIT 20""")
p("\nSelf-referencing examples:")
p(f"  {'Name':<50} {'emp_id':<12} {'fnum':>6} {'Wkrs':>8} {'St':>3}")
p(f"  {'-'*82}")
for r in cur.fetchall():
    p(f"  {r['employer_name'][:50]:<50} {r['employer_id']:<12} {r['latest_union_fnum'] or '':>6} {r['latest_unit_size'] or 0:>8,} {r['state'] or '':>3}")

cur.execute("""SELECT employer_name, state, latest_unit_size, latest_union_name
    FROM _cand WHERE NOT self_ref AND latest_union_name IS NOT NULL AND latest_unit_size > 0
    ORDER BY latest_unit_size DESC LIMIT 15""")
p("\n-- Unions employing staff represented by a DIFFERENT union --")
p(f"  {'Employer (a union)':<45} {'St':>2} {'Wkrs':>7} {'Representing Union':<30}")
p(f"  {'-'*88}")
for r in cur.fetchall():
    p(f"  {r['employer_name'][:45]:<45} {r['state'] or '':>2} {r['latest_unit_size'] or 0:>7,} {(r['latest_union_name'] or '')[:30]:<30}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('QUERY H: EXISTING FLAGS/COLUMNS')
p(SEP)

cur.execute("""SELECT column_name FROM information_schema.columns
    WHERE table_name = 'f7_employers_deduped'
    AND (column_name ILIKE '%%labor%%' OR column_name ILIKE '%%misclass%%')""")
cols = [c['column_name'] for c in cur.fetchall()]
p(f"labor/misclass columns: {cols if cols else 'NONE'}")

cur.execute("""SELECT data_quality_flag, COUNT(*) AS cnt FROM f7_employers_deduped
    WHERE data_quality_flag IS NOT NULL GROUP BY 1 ORDER BY cnt DESC""")
rows = cur.fetchall()
p(f"data_quality_flag: {dict((r['data_quality_flag'], r['cnt']) for r in rows) if rows else 'NONE SET'}")

cur.execute("""SELECT exclude_reason, COUNT(*) AS cnt FROM f7_employers_deduped
    WHERE exclude_reason IS NOT NULL GROUP BY 1 ORDER BY cnt DESC""")
rows = cur.fetchall()
p(f"exclude_reason: {dict((r['exclude_reason'], r['cnt']) for r in rows) if rows else 'NONE SET'}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('ADDITIONAL ANALYSIS')
p(SEP)

cur.execute("""SELECT employer_name, state, latest_unit_size, n_unions
    FROM _cand WHERE n_unions > 1 ORDER BY n_unions DESC LIMIT 15""")
p("\n-- Multi-union employers (strong legit employer signal) --")
p(f"  {'Employer':<50} {'St':>2} {'Wkrs':>7} {'#U':>4}")
p(f"  {'-'*66}")
for r in cur.fetchall():
    p(f"  {r['employer_name'][:50]:<50} {r['state'] or '':>2} {r['latest_unit_size'] or 0:>7,} {r['n_unions']:>4}")

cur.execute("""SELECT COALESCE(is_historical, FALSE) AS h, COUNT(*) AS cnt, SUM(COALESCE(latest_unit_size, 0)) AS w
    FROM _cand GROUP BY 1""")
p("\nHistorical vs Current:")
for r in cur.fetchall():
    p(f"  {'Historical' if r['h'] else 'Current':<12}: {r['cnt']:,} employers, {r['w']:,} workers")

cur.execute("""SELECT CASE WHEN COALESCE(filing_count,0)=0 THEN '0' WHEN filing_count=1 THEN '1'
    WHEN filing_count<=5 THEN '2-5' WHEN filing_count<=10 THEN '6-10' ELSE '10+' END AS b,
    COUNT(*) AS cnt FROM _cand GROUP BY 1 ORDER BY MIN(COALESCE(filing_count,0))""")
p("\nFiling count distribution:")
for r in cur.fetchall():
    p(f"  {r['b']:<8}: {r['cnt']:,}")

cur.execute("""SELECT LEFT(naics, 2) AS n2, COUNT(*) AS cnt
    FROM _cand WHERE naics IS NOT NULL GROUP BY 1 ORDER BY cnt DESC LIMIT 15""")
p("\nTop NAICS 2-digit sectors:")
for r in cur.fetchall():
    p(f"  {r['n2']}: {r['cnt']:,}")

# Affiliations -- do this in Python since cross-join is slow
p("\nUnion affiliations of these employer-names:")
cur.execute("SELECT employer_id, LOWER(TRIM(employer_name)) AS n FROM _cand")
cand_names = {r['employer_id']: r['n'] for r in cur.fetchall()}

cur.execute("""SELECT LOWER(TRIM(union_name)) AS n, aff_abbr FROM unions_master WHERE aff_abbr IS NOT NULL
    UNION SELECT LOWER(TRIM(f7_union_name)) AS n, aff_abbr FROM unions_master WHERE f7_union_name IS NOT NULL AND aff_abbr IS NOT NULL""")
name_to_aff = {}
for r in cur.fetchall():
    name_to_aff[r['n']] = r['aff_abbr']

from collections import Counter
aff_counts = Counter()
for eid, n in cand_names.items():
    aff = name_to_aff.get(n)
    if aff:
        aff_counts[aff] += 1

p(f"  {'Aff':<12} {'Count':>7}")
p(f"  {'-'*22}")
for aff, cnt in aff_counts.most_common(20):
    p(f"  {aff:<12} {cnt:>7,}")

# ══════════════════════════════════════════════════════════════════════════════
p(f"\n{SEP}")
p('CLASSIFICATION SIGNAL SUMMARY')
p(SEP)

cur.execute("""SELECT COUNT(*) AS total,
    COUNT(CASE WHEN has_uml THEN 1 END) AS ext,
    COUNT(CASE WHEN n_unions > 1 THEN 1 END) AS mu,
    COUNT(CASE WHEN has_f7 THEN 1 END) AS f7,
    COUNT(CASE WHEN NOT self_ref AND latest_union_name IS NOT NULL AND latest_unit_size > 0 THEN 1 END) AS du,
    COUNT(CASE WHEN self_ref AND NOT has_uml AND n_unions <= 1 THEN 1 END) AS sr_no_ext,
    COUNT(CASE WHEN COALESCE(latest_unit_size, 0) = 0 THEN 1 END) AS nw
    FROM _cand""")
row = cur.fetchone()
p(f"Total candidates:                              {row['total']:,}")
p(f"Has external data (OSHA/WHD/SAM/etc):          {row['ext']:,}")
p(f"Multiple unions represent workers:             {row['mu']:,}")
p(f"Has ANY F-7 relations:                         {row['f7']:,}")
p(f"Different union represents, with workers:      {row['du']:,}")
p(f"Self-ref, no external, <=1 union:              {row['sr_no_ext']:,}")
p(f"No workers at all:                             {row['nw']:,}")

p("\nCross-tab (has_uml x self_ref x has_workers):")
cur.execute("""SELECT has_uml, self_ref,
    CASE WHEN COALESCE(latest_unit_size, 0) > 0 THEN TRUE ELSE FALSE END AS hw,
    COUNT(*) AS cnt, SUM(COALESCE(latest_unit_size, 0)) AS w
    FROM _cand GROUP BY 1, 2, 3 ORDER BY has_uml DESC, self_ref, hw DESC""")
p(f"  {'UML':>5} {'Self':>5} {'Wkrs?':>6} {'Count':>8} {'TotalW':>10}")
p(f"  {'-'*38}")
for r in cur.fetchall():
    p(f"  {str(r['has_uml']):>5} {str(r['self_ref']):>5} {str(r['hw']):>6} {r['cnt']:>8,} {r['w']:>10,}")

conn.close()
p(f"\n{SEP}")
p("RESEARCH COMPLETE - No data was modified.")
p(SEP)
