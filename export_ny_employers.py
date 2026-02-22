"""Export all NY employers and their unions to CSV from all data sources."""
import csv
from db_config import get_connection

conn = get_connection()
cur = conn.cursor()

output_file = "ny_employers_unions.csv"
rows = []

# 1. F7 employers in NY with union info
print("Pulling F7 employers...")
cur.execute("""
    SELECT
        e.employer_id,
        e.employer_name,
        e.city,
        e.state,
        e.zip,
        e.naics,
        e.latest_unit_size,
        e.latest_notice_date,
        e.latest_union_name,
        e.latest_union_fnum,
        um.aff_abbr,
        um.sector AS union_sector,
        CASE
            WHEN um.sector IN ('PRIVATE', 'OTHER', 'RAILROAD_AIRLINE_RLA') THEN 'Private'
            WHEN um.sector IN ('PUBLIC_SECTOR', 'FEDERAL') THEN 'Public'
            ELSE 'Private'  -- F7 is overwhelmingly private-sector data
        END AS effective_sector
    FROM f7_employers_deduped e
    LEFT JOIN unions_master um ON e.latest_union_fnum::text = um.f_num::text
    WHERE e.state = 'NY'
    ORDER BY e.latest_unit_size DESC NULLS LAST
""")
f7_cols = [d[0] for d in cur.description]
f7_rows = cur.fetchall()
print(f"  {len(f7_rows)} F7 employers")

for r in f7_rows:
    d = dict(zip(f7_cols, r))
    rows.append({
        'source': 'F7_OLMS',
        'employer_name': d['employer_name'],
        'city': d['city'],
        'state': d['state'],
        'zip': d['zip'],
        'naics': d['naics'],
        'workers_or_members': d['latest_unit_size'],
        'union_name': d['latest_union_name'],
        'union_fnum': d['latest_union_fnum'],
        'affiliation': d['aff_abbr'],
        'sector': d['effective_sector'],
        'union_olms_sector': d['union_sector'],
        'date': str(d['latest_notice_date']) if d['latest_notice_date'] else '',
        'recognition_type': 'F7_FILING',
        'case_number': '',
        'employer_id': d['employer_id'],
    })

# 2. Manual employers in NY
print("Pulling manual employers...")
cur.execute("""
    SELECT employer_name, city, state, union_name, affiliation, local_number,
           num_employees, recognition_type, recognition_date, naics_sector, sector, source_type
    FROM manual_employers WHERE state = 'NY'
    ORDER BY num_employees DESC NULLS LAST
""")
manual_cols = [d[0] for d in cur.description]
manual_rows = cur.fetchall()
print(f"  {len(manual_rows)} manual employers")

for r in manual_rows:
    d = dict(zip(manual_cols, r))
    rows.append({
        'source': 'MANUAL',
        'employer_name': d['employer_name'],
        'city': d['city'],
        'state': d['state'],
        'zip': '',
        'naics': d['naics_sector'] or '',
        'workers_or_members': d['num_employees'],
        'union_name': d['union_name'],
        'union_fnum': '',
        'affiliation': d['affiliation'],
        'sector': 'Public' if (d['sector'] or '').upper() == 'PUBLIC' else 'Private',
        'union_olms_sector': '',
        'date': str(d['recognition_date']) if d['recognition_date'] else '',
        'recognition_type': d['recognition_type'] or d['source_type'] or 'MANUAL',
        'case_number': '',
        'employer_id': '',
    })

# 3. NLRB Voluntary Recognition in NY
print("Pulling NLRB VR...")
cur.execute("""
    SELECT employer_name, unit_city, unit_state, union_name, extracted_affiliation,
           num_employees, date_voluntary_recognition, vr_case_number, matched_employer_id,
           matched_union_fnum, unit_description
    FROM nlrb_voluntary_recognition WHERE unit_state = 'NY'
    ORDER BY num_employees DESC NULLS LAST
""")
vr_cols = [d[0] for d in cur.description]
vr_rows = cur.fetchall()
print(f"  {len(vr_rows)} VR cases")

for r in vr_rows:
    d = dict(zip(vr_cols, r))
    rows.append({
        'source': 'NLRB_VR',
        'employer_name': d['employer_name'],
        'city': d['unit_city'],
        'state': d['unit_state'],
        'zip': '',
        'naics': '',
        'workers_or_members': d['num_employees'],
        'union_name': d['union_name'],
        'union_fnum': d['matched_union_fnum'] or '',
        'affiliation': d['extracted_affiliation'] or '',
        'sector': 'Private',
        'union_olms_sector': '',
        'date': str(d['date_voluntary_recognition']) if d['date_voluntary_recognition'] else '',
        'recognition_type': 'VOLUNTARY_RECOGNITION',
        'case_number': d['vr_case_number'],
        'employer_id': d['matched_employer_id'] or '',
    })

# 4. NLRB Elections won in NY
print("Pulling NLRB election wins...")
cur.execute("""
    SELECT DISTINCT ON (p_emp.case_number)
        p_emp.participant_name AS employer_name,
        p_emp.city,
        p_emp.state,
        p_emp.zip,
        e.eligible_voters,
        e.election_date,
        e.case_number,
        p_emp.matched_employer_id,
        p_union.participant_name AS union_name,
        p_union.matched_olms_fnum AS union_fnum
    FROM nlrb_elections e
    JOIN nlrb_participants p_emp ON e.case_number = p_emp.case_number
        AND p_emp.participant_type = 'Employer'
    LEFT JOIN nlrb_participants p_union ON e.case_number = p_union.case_number
        AND p_union.participant_type IN ('Petitioner', 'Labor Organization / Union 1')
    WHERE p_emp.state = 'NY' AND e.union_won = true
    ORDER BY p_emp.case_number, e.election_date DESC
""")
elec_cols = [d[0] for d in cur.description]
elec_rows = cur.fetchall()
print(f"  {len(elec_rows)} election wins")

for r in elec_rows:
    d = dict(zip(elec_cols, r))
    rows.append({
        'source': 'NLRB_ELECTION_WIN',
        'employer_name': d['employer_name'],
        'city': d['city'],
        'state': d['state'],
        'zip': d['zip'] or '',
        'naics': '',
        'workers_or_members': d['eligible_voters'],
        'union_name': d['union_name'],
        'union_fnum': d['union_fnum'] or '',
        'affiliation': '',
        'sector': 'Private',
        'union_olms_sector': '',
        'date': str(d['election_date']) if d['election_date'] else '',
        'recognition_type': 'NLRB_ELECTION_WIN',
        'case_number': d['case_number'],
        'employer_id': d['matched_employer_id'] or '',
    })

# Write CSV
print(f"\nWriting {len(rows)} total rows to {output_file}...")
fieldnames = [
    'source', 'employer_name', 'city', 'state', 'zip', 'naics',
    'workers_or_members', 'union_name', 'union_fnum', 'affiliation',
    'sector', 'union_olms_sector', 'date', 'recognition_type',
    'case_number', 'employer_id'
]

with open(output_file, 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(rows)

print(f"Done! Wrote {output_file}")

# Summary
print("\n=== Summary by source ===")
from collections import Counter
src_counts = Counter(r['source'] for r in rows)
for src, cnt in src_counts.most_common():
    print(f"  {src}: {cnt}")

sec_counts = Counter(r['sector'] for r in rows)
print("\n=== Summary by sector ===")
for sec, cnt in sec_counts.most_common():
    print(f"  {sec}: {cnt}")

cur.close()
conn.close()
