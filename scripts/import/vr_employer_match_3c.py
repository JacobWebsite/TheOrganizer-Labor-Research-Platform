"""
VR Employer Matching - Checkpoint 3C
Verification and match quality report
Enhanced with token similarity verification
"""
import psycopg2
from psycopg2.extras import RealDictCursor
from name_normalizer import employer_token_similarity, extract_employer_key_words

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

print("=" * 60)
print("VR Employer Matching - Checkpoint 3C: Verification (Enhanced)")
print("=" * 60)

# Overall stats
cur.execute("""
    SELECT 
        COUNT(*) as total,
        COUNT(matched_employer_id) as matched,
        COUNT(*) - COUNT(matched_employer_id) as unmatched,
        COUNT(CASE WHEN employer_match_confidence >= 0.9 THEN 1 END) as high_conf,
        COUNT(CASE WHEN employer_match_confidence >= 0.7 AND employer_match_confidence < 0.9 THEN 1 END) as med_conf,
        COUNT(CASE WHEN employer_match_confidence < 0.7 THEN 1 END) as low_conf
    FROM nlrb_voluntary_recognition
""")
stats = cur.fetchone()

print(f"\nOverall Match Results:")
print(f"  Total VR records:    {stats['total']}")
print(f"  Matched:             {stats['matched']} ({100*stats['matched']/stats['total']:.1f}%)")
print(f"  Unmatched:           {stats['unmatched']} ({100*stats['unmatched']/stats['total']:.1f}%)")
print(f"\nConfidence Distribution:")
print(f"  High (>=0.9):        {stats['high_conf']}")
print(f"  Medium (0.7-0.9):    {stats['med_conf']}")
print(f"  Low (<0.7):          {stats['low_conf']}")

# By match method
print(f"\nBy Match Method:")
cur.execute("""
    SELECT 
        employer_match_method,
        COUNT(*) as cnt,
        ROUND(AVG(employer_match_confidence), 2) as avg_conf,
        SUM(COALESCE(num_employees, 0)) as total_emp
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NOT NULL
    GROUP BY employer_match_method
    ORDER BY cnt DESC
""")
for row in cur.fetchall():
    print(f"  {row['employer_match_method']:25} {row['cnt']:4} matches, {row['total_emp']:6} employees")

# Unmatched analysis
print(f"\nUnmatched Records Analysis:")
cur.execute("""
    SELECT 
        COUNT(*) as total_unmatched,
        COUNT(unit_state) as with_state,
        COUNT(unit_city) as with_city,
        COUNT(num_employees) as with_emp_count,
        SUM(COALESCE(num_employees, 0)) as total_emp
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NULL
""")
unm = cur.fetchone()
print(f"  Total unmatched:     {unm['total_unmatched']}")
print(f"  With state data:     {unm['with_state']}")
print(f"  With city data:      {unm['with_city']}")
print(f"  With employee count: {unm['with_emp_count']}")
print(f"  Total employees:     {unm['total_emp']:,}")

# Top unmatched employers (likely new to organizing)
print(f"\nTop Unmatched Employers (New to Organizing):")
cur.execute("""
    SELECT 
        employer_name_normalized,
        unit_city, unit_state,
        extracted_affiliation,
        num_employees,
        date_vr_request_received
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NULL
      AND num_employees IS NOT NULL
    ORDER BY num_employees DESC
    LIMIT 15
""")
for row in cur.fetchall():
    loc = f"{row['unit_city']}, {row['unit_state']}" if row['unit_city'] else row['unit_state'] or 'Unknown'
    print(f"  {row['employer_name_normalized'][:40]:40} | {loc:20} | {row['extracted_affiliation']:12} | {row['num_employees']} emp")

# Match quality spot check with token similarity verification
print(f"\nMatch Quality Spot Check (with verification):")
cur.execute("""
    SELECT
        vr.employer_name_normalized as vr_name,
        vr.unit_city as vr_city, vr.unit_state as vr_state,
        f7.employer_name as f7_name,
        f7.city as f7_city, f7.state as f7_state,
        vr.employer_match_method,
        vr.employer_match_confidence
    FROM nlrb_voluntary_recognition vr
    JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    ORDER BY RANDOM()
    LIMIT 10
""")
for row in cur.fetchall():
    vr_loc = f"{row['vr_city']}, {row['vr_state']}" if row['vr_city'] else 'N/A'
    f7_loc = f"{row['f7_city']}, {row['f7_state']}" if row['f7_city'] else 'N/A'
    # Calculate token similarity for verification
    tsim = employer_token_similarity(row['vr_name'] or '', row['f7_name'] or '')
    quality = "GOOD" if tsim >= 0.5 else ("FAIR" if tsim >= 0.3 else "CHECK")
    state_match = "Y" if row['vr_state'] == row['f7_state'] else "N"
    print(f"  VR:  {(row['vr_name'] or '')[:35]:35} ({vr_loc})")
    print(f"  F7:  {(row['f7_name'] or '')[:35]:35} ({f7_loc})")
    print(f"       Method: {row['employer_match_method']}, Conf: {row['employer_match_confidence']}, TokenSim: {tsim:.2f} [{quality}] State: {state_match}")
    print()

# Quality analysis by method
print(f"\nMatch Quality Analysis by Method:")
cur.execute("""
    SELECT employer_match_method, COUNT(*) as cnt
    FROM nlrb_voluntary_recognition
    WHERE matched_employer_id IS NOT NULL
    GROUP BY employer_match_method
    ORDER BY cnt DESC
""")
methods = cur.fetchall()

for method_row in methods:
    method = method_row['employer_match_method']
    # Sample some matches for this method
    cur.execute("""
        SELECT
            vr.employer_name_normalized as vr_name,
            f7.employer_name as f7_name
        FROM nlrb_voluntary_recognition vr
        JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
        WHERE vr.employer_match_method = %s
        ORDER BY RANDOM()
        LIMIT 20
    """, (method,))
    samples = cur.fetchall()

    if samples:
        avg_sim = sum(employer_token_similarity(s['vr_name'] or '', s['f7_name'] or '') for s in samples) / len(samples)
        quality = "HIGH" if avg_sim >= 0.5 else ("MED" if avg_sim >= 0.3 else "LOW")
        print(f"  {method:30} {method_row['cnt']:5} matches, avg token sim: {avg_sim:.2f} [{quality}]")

# Potential false positives
print(f"\nPotential False Positives (low token similarity):")
cur.execute("""
    SELECT
        vr.employer_name_normalized as vr_name,
        f7.employer_name as f7_name,
        vr.unit_state as vr_state,
        f7.state as f7_state,
        vr.employer_match_method,
        vr.employer_match_confidence
    FROM nlrb_voluntary_recognition vr
    JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    WHERE vr.employer_match_confidence < 0.75
    ORDER BY RANDOM()
    LIMIT 10
""")
false_pos_count = 0
for row in cur.fetchall():
    tsim = employer_token_similarity(row['vr_name'] or '', row['f7_name'] or '')
    if tsim < 0.25:
        false_pos_count += 1
        state_match = "same state" if row['vr_state'] == row['f7_state'] else "DIFF STATE"
        print(f"  VR:  {(row['vr_name'] or '')[:40]}")
        print(f"  F7:  {(row['f7_name'] or '')[:40]} ({state_match})")
        print(f"       Method: {row['employer_match_method']}, TokenSim: {tsim:.2f}")
        print()
if false_pos_count == 0:
    print("  No obvious false positives found in sample!")

# By affiliation - matched vs unmatched
print(f"\nMatch Rate by Union Affiliation:")
cur.execute("""
    SELECT 
        extracted_affiliation,
        COUNT(*) as total,
        COUNT(matched_employer_id) as matched,
        ROUND(100.0 * COUNT(matched_employer_id) / COUNT(*), 1) as match_pct
    FROM nlrb_voluntary_recognition
    GROUP BY extracted_affiliation
    HAVING COUNT(*) >= 10
    ORDER BY COUNT(*) DESC
""")
for row in cur.fetchall():
    print(f"  {row['extracted_affiliation']:15} {row['total']:4} total, {row['matched']:4} matched ({row['match_pct']}%)")

# By year - matched vs unmatched
print(f"\nMatch Rate by Year:")
cur.execute("""
    SELECT 
        EXTRACT(YEAR FROM date_vr_request_received)::int as year,
        COUNT(*) as total,
        COUNT(matched_employer_id) as matched,
        ROUND(100.0 * COUNT(matched_employer_id) / COUNT(*), 1) as match_pct
    FROM nlrb_voluntary_recognition
    WHERE date_vr_request_received IS NOT NULL
    GROUP BY EXTRACT(YEAR FROM date_vr_request_received)
    ORDER BY year
""")
for row in cur.fetchall():
    bar = '*' * int(row['match_pct'] / 5)
    print(f"  {row['year']}: {row['total']:4} total, {row['matched']:4} matched ({row['match_pct']:5.1f}%) {bar}")

cur.close()
conn.close()

print(f"\n{'=' * 60}")
print("CHECKPOINT 3 COMPLETE - EMPLOYER MATCHING FINISHED")
print(f"{'=' * 60}")
print(f"\nFinal Results:")
print(f"  Total VR records:      {stats['total']}")
print(f"  Employers matched:     {stats['matched']} ({100*stats['matched']/stats['total']:.1f}%)")
print(f"  New employers (unmatched): {stats['unmatched']} ({100*stats['unmatched']/stats['total']:.1f}%)")
print(f"\nNote: Unmatched employers likely represent NEW organizing")
print(f"      that hasn't yet resulted in F-7 contract filings.")
print(f"\nNext: Checkpoint 4 - Union Matching")
