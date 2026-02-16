"""Quick investigation: canonical groups + union shop problem."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db_config import get_connection

import psycopg2.extras
conn = get_connection()
cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

SEP = '=' * 70

print(SEP)
print('1. TOP 10 CANONICAL GROUPS BY MEMBER COUNT')
print(SEP)
cur.execute("""
    SELECT canonical_name, state, member_count, consolidated_workers, is_cross_state
    FROM employer_canonical_groups
    ORDER BY member_count DESC LIMIT 10
""")
for r in cur.fetchall():
    print(f"  {(r['canonical_name'] or '')[:50]:<50} st={r['state'] or 'multi':<6} members={r['member_count']:<4} workers={r['consolidated_workers'] or 0:>8,} cross={r['is_cross_state']}")

print('\n' + SEP)
print('2. SAG-AFTRA SIGNATORY ENTRIES')
print(SEP)
cur.execute("""
    SELECT employer_id, employer_name, state, latest_unit_size,
           exclude_from_counts, exclude_reason, canonical_group_id, is_canonical_rep
    FROM f7_employers_deduped
    WHERE employer_name ILIKE '%%signator%%' OR exclude_reason ILIKE '%%signator%%'
    ORDER BY latest_unit_size DESC NULLS LAST LIMIT 30
""")
rows = cur.fetchall()
print(f'Found {len(rows)} rows')
for r in rows:
    print(f"  {(r['employer_name'] or '')[:55]:<55} st={r['state'] or '??':<4} size={r['latest_unit_size'] or 0:>8,} excl={r['exclude_from_counts']} reason={r['exclude_reason'] or ''}")

print('\n' + SEP)
print('3. SCORECARD: has_f7_match breakdown (F7 = already unionized)')
print(SEP)
cur.execute("""
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE has_f7_match = TRUE) AS f7_true,
           COUNT(*) FILTER (WHERE has_f7_match = FALSE OR has_f7_match IS NULL) AS f7_false
    FROM mv_organizing_scorecard
""")
r = cur.fetchone()
print(f"  Total scorecard rows:    {r['total']:,}")
print(f"  has_f7_match = TRUE:     {r['f7_true']:,}  <-- these are UNION SHOPS being scored as targets")
print(f"  has_f7_match = FALSE:    {r['f7_false']:,}")
print(f"  Union share:             {r['f7_true']*100.0/r['total']:.1f}%")

print('\n' + SEP)
print('4. F7 EMPLOYERS ALSO IN SCORECARD (the misclassification)')
print(SEP)
cur.execute("""
    SELECT COUNT(DISTINCT d.employer_id) AS f7_in_scorecard
    FROM f7_employers_deduped d
    JOIN osha_f7_matches m ON m.f7_employer_id = d.employer_id
    JOIN mv_organizing_scorecard s ON s.establishment_id = m.establishment_id
""")
r = cur.fetchone()
print(f"  F7 employers with scorecard establishments: {r['f7_in_scorecard']:,}")

cur.execute("""
    SELECT COUNT(DISTINCT m.establishment_id) AS estabs
    FROM osha_f7_matches m
    JOIN mv_organizing_scorecard s ON s.establishment_id = m.establishment_id
""")
r = cur.fetchone()
print(f"  Scorecard estabs matched to F7:             {r['estabs']:,}")

# Show examples with score breakdown
cur.execute("""
    SELECT d.employer_name, d.state, d.latest_unit_size,
           s.estab_name, s.score_company_unions, s.score_industry_density,
           s.score_geographic, s.score_size, s.score_osha, s.has_f7_match
    FROM f7_employers_deduped d
    JOIN osha_f7_matches m ON m.f7_employer_id = d.employer_id
    JOIN mv_organizing_scorecard s ON s.establishment_id = m.establishment_id
    WHERE d.exclude_from_counts = FALSE
    ORDER BY d.latest_unit_size DESC NULLS LAST LIMIT 10
""")
print('\n  Top 10 F7 employers appearing in scorecard:')
for r in cur.fetchall():
    total_score = sum(v or 0 for v in [r['score_company_unions'], r['score_industry_density'], r['score_geographic'], r['score_size'], r['score_osha']])
    print(f"    {(r['employer_name'] or '')[:40]:<40} {r['state'] or '??':<4} f7_workers={r['latest_unit_size'] or 0:>7,} score={total_score:>3} f7_match={r['has_f7_match']}")

print('\n' + SEP)
print('5. TERRITORY: CA inflation')
print(SEP)
cur.execute("""
    SELECT COUNT(*) AS total,
           COUNT(*) FILTER (WHERE exclude_from_counts = FALSE) AS non_excluded,
           COUNT(*) FILTER (WHERE is_historical = FALSE) AS current_only,
           COUNT(*) FILTER (WHERE is_historical = FALSE AND exclude_from_counts = FALSE) AS current_non_excluded
    FROM f7_employers_deduped WHERE state = 'CA'
""")
r = cur.fetchone()
print(f"  CA total rows:                     {r['total']:,}")
print(f"  CA non-excluded:                   {r['non_excluded']:,}")
print(f"  CA current only:                   {r['current_only']:,}")
print(f"  CA current + non-excluded:         {r['current_non_excluded']:,}")

cur.execute("""
    SELECT COUNT(DISTINCT COALESCE(canonical_group_id::text, employer_id)) AS entities
    FROM f7_employers_deduped
    WHERE state = 'CA' AND is_historical = FALSE AND exclude_from_counts = FALSE
""")
print(f"  CA canonical entities (cur+clean): {cur.fetchone()['entities']:,}")

conn.close()
print('\nDone.')
