import os
import psycopg2

conn = psycopg2.connect(
    host='localhost',
    dbname='olms_multiyear',
    user='postgres',
    password='os.environ.get('DB_PASSWORD', '')'
)
cur = conn.cursor()

print('=' * 80)
print('CREATING DATABASE TABLES AND VIEWS FOR COVERAGE ANALYSIS')
print('=' * 80)

# 1. Create EPI state benchmarks table
print('\n1. Creating epi_state_benchmarks table...')
cur.execute('''
    DROP TABLE IF EXISTS epi_state_benchmarks CASCADE;
    
    CREATE TABLE epi_state_benchmarks (
        state VARCHAR(2) PRIMARY KEY,
        state_name VARCHAR(50),
        epi_private_members INTEGER,
        epi_public_members INTEGER,
        epi_total_members INTEGER,
        benchmark_year INTEGER DEFAULT 2024,
        source_notes TEXT,
        created_at TIMESTAMP DEFAULT NOW()
    );
    
    COMMENT ON TABLE epi_state_benchmarks IS 'EPI State of Working America 2024 union membership benchmarks by state';
''')

# Insert EPI data
epi_data = [
    ('AK', 'Alaska', 20385, 32000), ('AL', 'Alabama', 78538, 61000),
    ('AR', 'Arkansas', 26025, 19000), ('AZ', 'Arizona', 65763, 52000),
    ('CA', 'California', 1091677, 1283000), ('CO', 'Colorado', 104024, 103000),
    ('CT', 'Connecticut', 113037, 156000), ('DC', 'District of Columbia', 17283, 21000),
    ('DE', 'Delaware', 12342, 25000), ('FL', 'Florida', 215919, 246000),
    ('GA', 'Georgia', 88818, 86000), ('HI', 'Hawaii', 63592, 84000),
    ('IA', 'Iowa', 51552, 41000), ('ID', 'Idaho', 21445, 21000),
    ('IL', 'Illinois', 382476, 352000), ('IN', 'Indiana', 188006, 82000),
    ('KS', 'Kansas', 43261, 40000), ('KY', 'Kentucky', 117846, 38000),
    ('LA', 'Louisiana', 34103, 34000), ('MA', 'Massachusetts', 228375, 266000),
    ('MD', 'Maryland', 110514, 214000), ('ME', 'Maine', 37730, 39000),
    ('MI', 'Michigan', 402477, 178000), ('MN', 'Minnesota', 197917, 179000),
    ('MO', 'Missouri', 147865, 85000), ('MS', 'Mississippi', 38530, 20000),
    ('MT', 'Montana', 25863, 30000), ('NC', 'North Carolina', 63643, 44000),
    ('ND', 'North Dakota', 10265, 8000), ('NE', 'Nebraska', 24504, 38000),
    ('NH', 'New Hampshire', 27381, 35000), ('NJ', 'New Jersey', 352849, 327000),
    ('NM', 'New Mexico', 25697, 37000), ('NV', 'Nevada', 106416, 59000),
    ('NY', 'New York', 781226, 925000), ('OH', 'Ohio', 351676, 270000),
    ('OK', 'Oklahoma', 34430, 57000), ('OR', 'Oregon', 151290, 142000),
    ('PA', 'Pennsylvania', 344832, 322000), ('RI', 'Rhode Island', 36660, 36000),
    ('SC', 'South Carolina', 26931, 34000), ('SD', 'South Dakota', 4965, 7000),
    ('TN', 'Tennessee', 78333, 57000), ('TX', 'Texas', 308806, 293000),
    ('UT', 'Utah', 26912, 31000), ('VA', 'Virginia', 84702, 123000),
    ('VT', 'Vermont', 19683, 23000), ('WA', 'Washington', 285629, 262000),
    ('WI', 'Wisconsin', 118440, 62000), ('WV', 'West Virginia', 30972, 30000),
    ('WY', 'Wyoming', 7136, 7000)
]

cur.executemany('''
    INSERT INTO epi_state_benchmarks (state, state_name, epi_private_members, epi_public_members, epi_total_members, source_notes)
    VALUES (%s, %s, %s, %s, %s + %s, 'Private: union_membership.csv; Public: Table 6b 12-month rolling avg')
''', [(s, n, p, pub, p, pub) for s, n, p, pub in epi_data])

print('   Inserted {} state benchmarks'.format(len(epi_data)))

# 2. Create state_coverage_comparison table
print('\n2. Creating state_coverage_comparison table...')
cur.execute('''
    DROP TABLE IF EXISTS state_coverage_comparison CASCADE;
    
    CREATE TABLE state_coverage_comparison (
        state VARCHAR(2) PRIMARY KEY,
        epi_private INTEGER,
        platform_private INTEGER,
        private_coverage_pct NUMERIC(6,1),
        epi_public INTEGER,
        platform_public INTEGER,
        public_coverage_pct NUMERIC(6,1),
        epi_total INTEGER,
        platform_total INTEGER,
        total_coverage_pct NUMERIC(6,1),
        private_flag VARCHAR(20),
        public_flag VARCHAR(20),
        last_updated TIMESTAMP DEFAULT NOW(),
        FOREIGN KEY (state) REFERENCES epi_state_benchmarks(state)
    );
    
    COMMENT ON TABLE state_coverage_comparison IS 'Platform coverage vs EPI benchmarks with diagnostic flags';
''')

# Insert coverage data with flags
coverage_data = [
    ('AK', 20385, 17799, 87.3, 32000, 5451, 17.0, 52385, 23250, 44.4, None, 'PUBLIC_GAP'),
    ('AL', 78538, 47316, 60.2, 61000, 0, 0.0, 139538, 47316, 33.9, 'PRIVATE_UNDER', 'NO_PUBLIC_DATA'),
    ('AR', 26025, 36387, 139.8, 19000, 7, 0.0, 45025, 36394, 80.8, 'PRIVATE_OVER', 'NO_PUBLIC_DATA'),
    ('AZ', 65763, 41789, 63.5, 52000, 3104, 6.0, 117763, 44893, 38.1, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('CA', 1091677, 897543, 82.2, 1283000, 898582, 70.0, 2374677, 1796125, 75.6, None, None),
    ('CO', 104024, 52633, 50.6, 103000, 23372, 22.7, 207024, 76005, 36.7, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('CT', 113037, 66021, 58.4, 156000, 183046, 117.3, 269037, 249067, 92.6, 'PRIVATE_UNDER', 'PUBLIC_OVER'),
    ('DC', 17283, 17762, 102.8, 21000, 1601844, 7627.8, 38283, 1619606, 4230.6, 'HQ_EFFECT', 'HQ_EFFECT'),
    ('DE', 12342, 10674, 86.5, 25000, 6063, 24.3, 37342, 16737, 44.8, None, 'PUBLIC_GAP'),
    ('FL', 215919, 125873, 58.3, 246000, 172370, 70.1, 461919, 298243, 64.6, 'PRIVATE_UNDER', None),
    ('GA', 88818, 104173, 117.3, 86000, 1416, 1.6, 174818, 105589, 60.4, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('HI', 63592, 36121, 56.8, 84000, 13147, 15.7, 147592, 49268, 33.4, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('IA', 51552, 59098, 114.6, 41000, 6756, 16.5, 92552, 65854, 71.2, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('ID', 21445, 27806, 129.7, 21000, 0, 0.0, 42445, 27806, 65.5, 'PRIVATE_OVER', 'NO_PUBLIC_DATA'),
    ('IL', 382476, 385269, 100.7, 352000, 604727, 171.8, 734476, 989996, 134.8, None, 'PUBLIC_OVER'),
    ('IN', 188006, 160236, 85.2, 82000, 6931, 8.5, 270006, 167167, 61.9, None, 'PUBLIC_GAP'),
    ('KS', 43261, 61310, 141.7, 40000, 1064, 2.7, 83261, 62374, 74.9, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('KY', 117846, 94923, 80.5, 38000, 400, 1.1, 155846, 95323, 61.2, None, 'PUBLIC_GAP'),
    ('LA', 34103, 33586, 98.5, 34000, 17163, 50.5, 68103, 50749, 74.5, None, None),
    ('MA', 228375, 160658, 70.3, 266000, 222838, 83.8, 494375, 383496, 77.6, None, None),
    ('MD', 110514, 118227, 107.0, 214000, 47634, 22.3, 324514, 165861, 51.1, None, 'PUBLIC_GAP'),
    ('ME', 37730, 7154, 19.0, 39000, 31869, 81.7, 76730, 39023, 50.9, 'PRIVATE_UNDER', None),
    ('MI', 402477, 321906, 80.0, 178000, 185564, 104.2, 580477, 507470, 87.4, None, None),
    ('MN', 197917, 270840, 136.8, 179000, 201107, 112.4, 376917, 471947, 125.2, 'PRIVATE_OVER', 'PUBLIC_OVER'),
    ('MO', 147865, 172455, 116.6, 85000, 18501, 21.8, 232865, 190956, 82.0, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('MS', 38530, 20957, 54.4, 20000, 40, 0.2, 58530, 20997, 35.9, 'PRIVATE_UNDER', 'NO_PUBLIC_DATA'),
    ('MT', 25863, 11014, 42.6, 30000, 25894, 86.3, 55863, 36908, 66.1, 'PRIVATE_UNDER', None),
    ('NC', 63643, 38693, 60.8, 44000, 5440, 12.4, 107643, 44133, 41.0, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('ND', 10265, 9162, 89.3, 8000, 35, 0.4, 18265, 9197, 50.4, None, 'NO_PUBLIC_DATA'),
    ('NE', 24504, 16181, 66.0, 38000, 755, 2.0, 62504, 16936, 27.1, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('NH', 27381, 7534, 27.5, 35000, 10229, 29.2, 62381, 17763, 28.5, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('NJ', 352849, 202921, 57.5, 327000, 86709, 26.5, 679849, 289630, 42.6, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
    ('NM', 25697, 32152, 125.1, 37000, 10294, 27.8, 62697, 42446, 67.7, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('NV', 106416, 107591, 101.1, 59000, 10216, 17.3, 165416, 117807, 71.2, None, 'PUBLIC_GAP'),
    ('NY', 781226, 723855, 92.7, 925000, 1337601, 144.6, 1706226, 2061456, 120.8, None, 'PUBLIC_OVER'),
    ('OH', 351676, 303364, 86.3, 270000, 229575, 85.0, 621676, 532939, 85.7, None, None),
    ('OK', 34430, 18621, 54.1, 57000, 495, 0.9, 91430, 19116, 20.9, 'PRIVATE_UNDER', 'NO_PUBLIC_DATA'),
    ('OR', 151290, 96670, 63.9, 142000, 135714, 95.6, 293290, 232384, 79.2, 'PRIVATE_UNDER', None),
    ('PA', 344832, 310114, 89.9, 322000, 453588, 140.9, 666832, 763702, 114.5, None, 'PUBLIC_OVER'),
    ('RI', 36660, 30882, 84.2, 36000, 35215, 97.8, 72660, 66097, 91.0, None, None),
    ('SC', 26931, 13124, 48.7, 34000, 0, 0.0, 60931, 13124, 21.5, 'PRIVATE_UNDER', 'NO_PUBLIC_DATA'),
    ('SD', 4965, 4197, 84.5, 7000, 0, 0.0, 11965, 4197, 35.1, None, 'NO_PUBLIC_DATA'),
    ('TN', 78333, 66565, 85.0, 57000, 7487, 13.1, 135333, 74052, 54.7, None, 'PUBLIC_GAP'),
    ('TX', 308806, 331971, 107.5, 293000, 22944, 7.8, 601806, 354915, 59.0, None, 'PUBLIC_GAP'),
    ('UT', 26912, 35562, 132.1, 31000, 0, 0.0, 57912, 35562, 61.4, 'PRIVATE_OVER', 'NO_PUBLIC_DATA'),
    ('VA', 84702, 104435, 123.3, 123000, 4732, 3.8, 207702, 109167, 52.6, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('VT', 19683, 4472, 22.7, 23000, 27416, 119.2, 42683, 31888, 74.7, 'PRIVATE_UNDER', 'PUBLIC_OVER'),
    ('WA', 285629, 291207, 102.0, 262000, 223488, 85.3, 547629, 514695, 94.0, None, None),
    ('WI', 118440, 145922, 123.2, 62000, 14268, 23.0, 180440, 160190, 88.8, 'PRIVATE_OVER', 'PUBLIC_GAP'),
    ('WV', 30972, 33597, 108.5, 30000, 4999, 16.7, 60972, 38596, 63.3, None, 'PUBLIC_GAP'),
    ('WY', 7136, 1860, 26.1, 7000, 373, 5.3, 14136, 2233, 15.8, 'PRIVATE_UNDER', 'PUBLIC_GAP'),
]

cur.executemany('''
    INSERT INTO state_coverage_comparison VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
''', coverage_data)

print('   Inserted {} state coverage records'.format(len(coverage_data)))

# 3. Create live coverage view
print('\n3. Creating v_state_coverage_live view...')
cur.execute('''
    DROP VIEW IF EXISTS v_state_coverage_live CASCADE;
    
    CREATE VIEW v_state_coverage_live AS
    WITH private_reconciled AS (
        SELECT 
            v.state,
            SUM(CASE
                WHEN v.affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'AFT') THEN 0
                WHEN v.match_type = 'NAME_INFERRED' THEN ROUND(v.f7_reported_workers * 0.15)
                WHEN v.match_type = 'UNMATCHED' THEN ROUND(v.f7_reported_workers * 0.35)
                ELSE v.estimated_actual_workers
            END) as platform_private
        FROM v_f7_employers_fully_adjusted v
        JOIN f7_employers e ON v.employer_id = e.employer_id
        WHERE v.state IS NOT NULL AND LENGTH(v.state) = 2
          AND NOT (v.affiliation IN ('AFGE', 'APWU', 'NALC', 'NFFE', 'NTEU', 'AFT'))
          AND NOT (e.latest_union_name ILIKE ANY(ARRAY['%Government Employees%', '%Treasury Employees%', '%Teachers%']))
          AND NOT (v.employer_name ILIKE ANY(ARRAY['%state of%', '%city of%', '%county of%', '%department of%']))
        GROUP BY v.state
    ),
    public_sector AS (
        SELECT 
            state,
            COALESCE(olms_state_local_members, 0) + COALESCE(flra_federal_workers, 0) as platform_public
        FROM public_sector_benchmarks
        WHERE state IS NOT NULL
    )
    SELECT 
        b.state,
        b.state_name,
        b.epi_private_members as epi_private,
        COALESCE(pr.platform_private, 0)::INTEGER as platform_private,
        ROUND(COALESCE(pr.platform_private, 0) * 100.0 / NULLIF(b.epi_private_members, 0), 1) as private_coverage_pct,
        b.epi_public_members as epi_public,
        COALESCE(ps.platform_public, 0) as platform_public,
        ROUND(COALESCE(ps.platform_public, 0) * 100.0 / NULLIF(b.epi_public_members, 0), 1) as public_coverage_pct,
        b.epi_total_members as epi_total,
        (COALESCE(pr.platform_private, 0) + COALESCE(ps.platform_public, 0))::INTEGER as platform_total,
        ROUND((COALESCE(pr.platform_private, 0) + COALESCE(ps.platform_public, 0)) * 100.0 / NULLIF(b.epi_total_members, 0), 1) as total_coverage_pct,
        CASE 
            WHEN b.state = 'DC' THEN 'HQ_EFFECT'
            WHEN COALESCE(pr.platform_private, 0) * 100.0 / NULLIF(b.epi_private_members, 0) > 130 THEN 'PRIVATE_OVER'
            WHEN COALESCE(pr.platform_private, 0) * 100.0 / NULLIF(b.epi_private_members, 0) < 50 THEN 'PRIVATE_UNDER'
            ELSE NULL
        END as private_flag,
        CASE 
            WHEN b.state = 'DC' THEN 'HQ_EFFECT'
            WHEN COALESCE(ps.platform_public, 0) < 100 THEN 'NO_PUBLIC_DATA'
            WHEN COALESCE(ps.platform_public, 0) * 100.0 / NULLIF(b.epi_public_members, 0) > 115 THEN 'PUBLIC_OVER'
            WHEN COALESCE(ps.platform_public, 0) * 100.0 / NULLIF(b.epi_public_members, 0) < 50 THEN 'PUBLIC_GAP'
            ELSE NULL
        END as public_flag
    FROM epi_state_benchmarks b
    LEFT JOIN private_reconciled pr ON b.state = pr.state
    LEFT JOIN public_sector ps ON b.state = ps.state
    ORDER BY b.state;
    
    COMMENT ON VIEW v_state_coverage_live IS 'Live calculation of platform coverage vs EPI benchmarks with auto-generated flags';
''')

print('   Created v_state_coverage_live')

# 4. Create anomalies view
print('\n4. Creating v_coverage_anomalies view...')
cur.execute('''
    DROP VIEW IF EXISTS v_coverage_anomalies CASCADE;
    
    CREATE VIEW v_coverage_anomalies AS
    SELECT 
        state,
        state_name,
        epi_private,
        platform_private,
        private_coverage_pct,
        private_flag,
        epi_public,
        platform_public,
        public_coverage_pct,
        public_flag,
        CASE 
            WHEN private_flag = 'PRIVATE_OVER' AND private_coverage_pct > 130 THEN 'CHECK_DOUBLE_COUNTING'
            WHEN private_flag = 'PRIVATE_UNDER' AND private_coverage_pct < 30 THEN 'MAJOR_COVERAGE_GAP'
            WHEN public_flag = 'NO_PUBLIC_DATA' THEN 'NEED_STATE_PERB_DATA'
            WHEN public_flag = 'PUBLIC_OVER' AND public_coverage_pct > 150 THEN 'CHECK_HQ_EFFECTS'
            ELSE 'INVESTIGATE'
        END as recommended_action
    FROM v_state_coverage_live
    WHERE private_flag IS NOT NULL OR public_flag IS NOT NULL
    ORDER BY 
        CASE WHEN private_flag = 'PRIVATE_OVER' THEN 1
             WHEN public_flag = 'PUBLIC_OVER' THEN 2
             WHEN private_flag = 'PRIVATE_UNDER' THEN 3
             WHEN public_flag = 'NO_PUBLIC_DATA' THEN 4
             ELSE 5 END,
        total_coverage_pct DESC;
    
    COMMENT ON VIEW v_coverage_anomalies IS 'States with coverage flags requiring investigation';
''')

print('   Created v_coverage_anomalies')

# 5. Create summary view
print('\n5. Creating v_coverage_summary view...')
cur.execute('''
    DROP VIEW IF EXISTS v_coverage_summary CASCADE;
    
    CREATE VIEW v_coverage_summary AS
    SELECT 
        'ALL_STATES' as scope,
        SUM(epi_private) as epi_private_total,
        SUM(platform_private) as platform_private_total,
        ROUND(SUM(platform_private) * 100.0 / SUM(epi_private), 1) as private_coverage_pct,
        SUM(epi_public) as epi_public_total,
        SUM(platform_public) as platform_public_total,
        ROUND(SUM(platform_public) * 100.0 / SUM(epi_public), 1) as public_coverage_pct,
        SUM(epi_total) as epi_total,
        SUM(platform_total) as platform_total,
        ROUND(SUM(platform_total) * 100.0 / SUM(epi_total), 1) as total_coverage_pct
    FROM v_state_coverage_live
    
    UNION ALL
    
    SELECT 
        'EXCLUDING_DC' as scope,
        SUM(epi_private) as epi_private_total,
        SUM(platform_private) as platform_private_total,
        ROUND(SUM(platform_private) * 100.0 / SUM(epi_private), 1) as private_coverage_pct,
        SUM(epi_public) as epi_public_total,
        SUM(platform_public) as platform_public_total,
        ROUND(SUM(platform_public) * 100.0 / SUM(epi_public), 1) as public_coverage_pct,
        SUM(epi_total) as epi_total,
        SUM(platform_total) as platform_total,
        ROUND(SUM(platform_total) * 100.0 / SUM(epi_total), 1) as total_coverage_pct
    FROM v_state_coverage_live
    WHERE state != 'DC';
    
    COMMENT ON VIEW v_coverage_summary IS 'National coverage totals with and without DC';
''')

print('   Created v_coverage_summary')

conn.commit()

# Test the views
print('\n' + '=' * 80)
print('TESTING VIEWS')
print('=' * 80)

print('\n--- v_coverage_summary ---')
cur.execute('SELECT * FROM v_coverage_summary')
for row in cur.fetchall():
    print(row)

print('\n--- v_coverage_anomalies (first 10) ---')
cur.execute('SELECT state, state_name, private_flag, public_flag, recommended_action FROM v_coverage_anomalies LIMIT 10')
for row in cur.fetchall():
    print(row)

cur.close()
conn.close()

print('\n' + '=' * 80)
print('COMPLETE!')
print('=' * 80)
print('''
Created:
  - epi_state_benchmarks (table): EPI 2024 benchmarks by state
  - state_coverage_comparison (table): Static coverage snapshot with flags
  - v_state_coverage_live (view): Live coverage calculation from current data
  - v_coverage_anomalies (view): States requiring investigation
  - v_coverage_summary (view): National totals with/without DC
''')
