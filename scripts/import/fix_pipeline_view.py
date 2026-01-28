import psycopg2
conn = psycopg2.connect(host='localhost', database='olms_multiyear', user='postgres', password='Juniordog33!')
conn.autocommit = True
cur = conn.cursor()

# Fix the pipeline view
cur.execute("""
    DROP VIEW IF EXISTS v_vr_to_f7_pipeline CASCADE;
    CREATE OR REPLACE VIEW v_vr_to_f7_pipeline AS
    SELECT 
        vr.id as vr_id,
        vr.vr_case_number,
        vr.employer_name_normalized as vr_employer,
        vr.date_vr_request_received as vr_date,
        vr.num_employees as vr_employees,
        vr.extracted_affiliation,
        f7.employer_id,
        f7.employer_name as f7_employer,
        f7.latest_notice_date::date as f7_date,
        f7.latest_unit_size as f7_employees,
        f7.latest_union_name as f7_union,
        (f7.latest_notice_date::date - vr.date_vr_request_received) as days_vr_to_f7,
        CASE 
            WHEN f7.latest_notice_date::date > vr.date_vr_request_received THEN 'VR preceded F7'
            WHEN f7.latest_notice_date::date < vr.date_vr_request_received THEN 'F7 preceded VR'
            ELSE 'Same period'
        END as sequence_type
    FROM nlrb_voluntary_recognition vr
    JOIN f7_employers_deduped f7 ON vr.matched_employer_id = f7.employer_id
    WHERE vr.date_vr_request_received IS NOT NULL
      AND f7.latest_notice_date IS NOT NULL
""")
print("Created v_vr_to_f7_pipeline")

cur.execute("SELECT COUNT(*) FROM v_vr_to_f7_pipeline")
print(f"  Rows: {cur.fetchone()[0]}")

cur.execute("""
    SELECT sequence_type, COUNT(*), AVG(days_vr_to_f7)::int as avg_days
    FROM v_vr_to_f7_pipeline
    GROUP BY sequence_type
""")
print("\nPipeline analysis:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]} cases, avg {row[2]} days")

conn.close()
