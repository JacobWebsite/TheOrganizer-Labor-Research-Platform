import sys
import os
sys.path.insert(0, 'C:/Users/jakew/Downloads/labor-data-project')
from db_config import get_connection

tables = [
    'ar_disbursements_emp_off', 'osha_violations_detail', 'nlrb_docket', 
    'qcew_annual', 'nlrb_participants', 'epi_union_membership', 
    'employers_990_deduped', 'osha_establishments', 'osha_violation_summary', 
    'sam_entities', 'nlrb_allegations', 'national_990_filers', 
    'sec_companies', 'gleif_ownership_links', 'nlrb_filings', 
    'nlrb_cases', 'gleif_us_entities', 'whd_cases', 'lm_data', 
    'ar_assets_investments', 'employer_comparables', 'unified_match_log', 
    'ar_membership', 'ar_disbursements_total', 'nlrb_employer_xref', 
    'union_names_crosswalk', 'f7_employers_deduped', 'f7_employers'
]

mvs = [
    'mv_whd_employer_agg', 'mv_organizing_scorecard', 'mv_employer_search', 
    'mv_employer_data_sources', 'mv_unified_scorecard', 'mv_employer_features'
]

conn = get_connection()
cur = conn.cursor()

print("| Type | Name | Row Count |")
print("|------|------|-----------|")

for table in tables:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"| Table | {table} | {count} |")
    except Exception as e:
        print(f"| Table | {table} | Error: {e} |")
        conn.rollback()
        cur = conn.cursor()

for mv in mvs:
    try:
        cur.execute(f"SELECT COUNT(*) FROM {mv}")
        count = cur.fetchone()[0]
        print(f"| MV | {mv} | {count} |")
    except Exception as e:
        print(f"| MV | {mv} | Error: {e} |")
        conn.rollback()
        cur = conn.cursor()

cur.close()
conn.close()
