import os
"""
VR Union Matching - Checkpoint 4C
Verification and match quality report
Enhanced reporting for new matching strategies
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import token_similarity, extract_key_tokens

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password=os.environ.get('DB_PASSWORD', '')
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("VR Union Matching - Checkpoint 4C: Verification (Enhanced)")
print("=" * 60)

# Overall stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_union_fnum) as matched,
        COUNT(*) - COUNT(matched_union_fnum) as unmatched,
        COUNT(CASE WHEN union_match_confidence >= 0.9 THEN 1 END) as high_conf,
        COUNT(CASE WHEN union_match_confidence >= 0.6 AND union_match_confidence < 0.9 THEN 1 END) as med_conf,
        COUNT(CASE WHEN union_match_confidence < 0.6 THEN 1 END) as low_conf
    FROM nlrb_voluntary_recognition
""")
stats = cur.fetchone()

print(f"\nOverall Union Match Results:")
print(f"  Total VR records:    {stats['total']}")
print(f"  Matched:             {stats['matched']} ({100*stats['matched']/stats['total']:.1f}%)")
print(f"  Unmatched:           {stats['unmatched']} ({100*stats['unmatched']/stats['total']:.1f}%)")
print(f"\nConfidence Distribution:")
print(f"  High (>=0.9):        {stats['high_conf']}")
print(f"  Medium (0.6-0.9):    {stats['med_conf']}")
print(f"  Low (<0.6):          {stats['low_conf']}")

# By match method
print(f"\nBy Match Method:")
cur.execute("""
    SELECT 
        union_match_method,
        COUNT(*) as cnt,
        ROUND(AVG(union_match_confidence), 2) as avg_conf,
        SUM(COALESCE(num_employees, 0)) as total_emp
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NOT NULL
    GROUP BY union_match_method
    ORDER BY cnt DESC
""")
for row in cur.fetchall():
    print(f"  {row['union_match_method']:25} {row['cnt']:4} matches, {row['total_emp']:6} employees")

# Unmatched analysis
print(f"\nUnmatched Records Analysis:")
cur.execute("""
    SELECT 
        COUNT(*) as total_unmatched,
        COUNT(CASE WHEN extracted_affiliation = 'INDEPENDENT' THEN 1 END) as independents,
        SUM(COALESCE(num_employees, 0)) as total_emp
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
""")
unm = cur.fetchone()
print(f"  Total unmatched:     {unm['total_unmatched']}")
print(f"  Independent unions:  {unm['independents']}")
print(f"  Total employees:     {unm['total_emp']:,}")

# Sample unmatched unions with analysis
print(f"\nSample Unmatched Unions (with analysis):")
cur.execute("""
    SELECT
        union_name,
        union_name_normalized,
        extracted_affiliation,
        extracted_local_number,
        num_employees,
        unit_state
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NULL
      AND num_employees IS NOT NULL
    ORDER BY num_employees DESC
    LIMIT 15
""")
for row in cur.fetchall():
    key_tokens = extract_key_tokens(row['union_name_normalized'] or '')
    print(f"  {(row['union_name_normalized'] or '')[:40]:40} | {row['extracted_affiliation'] or 'N/A':12} | Local: {row['extracted_local_number'] or 'N/A':6} | {row['num_employees']} emp")
    if key_tokens:
        print(f"    Key tokens: {', '.join(list(key_tokens)[:5])}")

# Potential false positives (low token similarity matches)
print(f"\nPotential False Positives (low token similarity):")
cur.execute("""
    SELECT
        vr.union_name_normalized as vr_union,
        um.union_name as olms_union,
        vr.union_match_method,
        vr.union_match_confidence
    FROM nlrb_voluntary_recognition vr
    JOIN unions_master um ON vr.matched_union_fnum = um.f_num
    WHERE vr.union_match_confidence < 0.7
    ORDER BY RANDOM()
    LIMIT 10
""")
false_pos_count = 0
for row in cur.fetchall():
    tsim = token_similarity(row['vr_union'] or '', row['olms_union'] or '')
    if tsim < 0.2:
        false_pos_count += 1
        print(f"  VR:   {(row['vr_union'] or '')[:45]}")
        print(f"  OLMS: {(row['olms_union'] or '')[:45]}")
        print(f"        Method: {row['union_match_method']}, TokenSim: {tsim:.2f}")
        print()
if false_pos_count == 0:
    print("  No obvious false positives found in sample!")

# Match quality spot check with token similarity verification
print(f"\nMatch Quality Spot Check (random sample with verification):")
cur.execute("""
    SELECT
        vr.union_name_normalized as vr_union,
        um.union_name as olms_union,
        um.aff_abbr,
        vr.union_match_method,
        vr.union_match_confidence
    FROM nlrb_voluntary_recognition vr
    JOIN unions_master um ON vr.matched_union_fnum = um.f_num
    ORDER BY RANDOM()
    LIMIT 10
""")
for row in cur.fetchall():
    # Calculate token similarity for verification
    tsim = token_similarity(row['vr_union'] or '', row['olms_union'] or '')
    quality = "GOOD" if tsim >= 0.4 else ("FAIR" if tsim >= 0.2 else "CHECK")
    print(f"  VR:   {(row['vr_union'] or '')[:50]}")
    print(f"  OLMS: {(row['olms_union'] or '')[:50]} ({row['aff_abbr']})")
    print(f"        Method: {row['union_match_method']}, Conf: {row['union_match_confidence']}, TokenSim: {tsim:.2f} [{quality}]")
    print()

# Quality analysis by method
print(f"\nMatch Quality Analysis by Method:")
cur.execute("""
    SELECT union_match_method, COUNT(*) as cnt
    FROM nlrb_voluntary_recognition
    WHERE matched_union_fnum IS NOT NULL
    GROUP BY union_match_method
    ORDER BY cnt DESC
""")
methods = cur.fetchall()

for method_row in methods:
    method = method_row['union_match_method']
    # Sample some matches for this method and calculate average token similarity
    cur.execute("""
        SELECT
            vr.union_name_normalized as vr_union,
            um.union_name as olms_union
        FROM nlrb_voluntary_recognition vr
        JOIN unions_master um ON vr.matched_union_fnum = um.f_num
        WHERE vr.union_match_method = %s
        ORDER BY RANDOM()
        LIMIT 20
    """, (method,))
    samples = cur.fetchall()

    if samples:
        avg_sim = sum(token_similarity(s['vr_union'] or '', s['olms_union'] or '') for s in samples) / len(samples)
        quality = "HIGH" if avg_sim >= 0.5 else ("MED" if avg_sim >= 0.3 else "LOW")
        print(f"  {method:30} {method_row['cnt']:5} matches, avg token sim: {avg_sim:.2f} [{quality}]")

# By affiliation - matched vs unmatched
print(f"\nMatch Rate by Extracted Affiliation:")
cur.execute("""
    SELECT 
        extracted_affiliation,
        COUNT(*) as total,
        COUNT(matched_union_fnum) as matched,
        ROUND(100.0 * COUNT(matched_union_fnum) / COUNT(*), 1) as match_pct
    FROM nlrb_voluntary_recognition
    GROUP BY extracted_affiliation
    HAVING COUNT(*) >= 5
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    bar = '*' * int(row['match_pct'] / 5)
    print(f"  {row['extracted_affiliation']:15} {row['total']:4} total, {row['matched']:4} matched ({row['match_pct']:5.1f}%) {bar}")

# Combined summary
print(f"\n{'=' * 60}")
print("COMBINED MATCHING SUMMARY")
print(f"{'=' * 60}")

cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_employer_id) as emp_matched,
        COUNT(matched_union_fnum) as union_matched,
        COUNT(CASE WHEN matched_employer_id IS NOT NULL AND matched_union_fnum IS NOT NULL THEN 1 END) as both_matched,
        SUM(COALESCE(num_employees, 0)) as total_employees
    FROM nlrb_voluntary_recognition
""")
combined = cur.fetchone()

print(f"\n  Total VR records:       {combined['total']}")
print(f"  Employer matched:       {combined['emp_matched']} ({100*combined['emp_matched']/combined['total']:.1f}%)")
print(f"  Union matched:          {combined['union_matched']} ({100*combined['union_matched']/combined['total']:.1f}%)")
print(f"  Both matched:           {combined['both_matched']} ({100*combined['both_matched']/combined['total']:.1f}%)")
print(f"  Total employees:        {combined['total_employees']:,}")

cur.close()
conn.close()

print(f"\n{'=' * 60}")
print("CHECKPOINT 4 COMPLETE - UNION MATCHING FINISHED")
print(f"{'=' * 60}")
print(f"\nFinal Results:")
print(f"  Union match rate:        {100*combined['union_matched']/combined['total']:.1f}%")
print(f"  Employer match rate:     {100*combined['emp_matched']/combined['total']:.1f}%")
print(f"  Fully linked records:    {100*combined['both_matched']/combined['total']:.1f}%")
print(f"\nNext: Checkpoint 5 - Integration Views")
