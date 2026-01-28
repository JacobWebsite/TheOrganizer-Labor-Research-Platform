"""
Export private sector coverage data to Excel
"""
import psycopg2
from psycopg2.extras import RealDictCursor
import pandas as pd

conn = psycopg2.connect(
    host='localhost',
    database='olms_multiyear',
    user='postgres',
    password='Juniordog33!'
)
cur = conn.cursor(cursor_factory=RealDictCursor)

# Improved classification with spelled-out names
CLASSIFICATION_SQL = '''
    CASE
        -- Teamsters
        WHEN latest_union_name ILIKE '%teamster%' OR latest_union_name ILIKE '%ibt%' THEN 'IBT (Teamsters)'

        -- SEIU (including 1199, UHWE, etc)
        WHEN latest_union_name ILIKE '%seiu%'
          OR latest_union_name ILIKE '%service employees international%'
          OR latest_union_name ILIKE '%1199%' THEN 'SEIU'

        -- UFCW
        WHEN latest_union_name ILIKE '%ufcw%'
          OR latest_union_name ILIKE '%united food%commercial%' THEN 'UFCW'

        -- UAW
        WHEN latest_union_name ILIKE '%uaw%'
          OR latest_union_name ILIKE '%united automobile%'
          OR latest_union_name ILIKE '%united auto%' THEN 'UAW'

        -- Carpenters
        WHEN latest_union_name ILIKE '%carpenter%'
          OR latest_union_name ILIKE '%cja%'
          OR latest_union_name ILIKE '%ubc%'
          OR latest_union_name ILIKE '%regional council of carpenter%' THEN 'UBC (Carpenters)'

        -- IBEW
        WHEN latest_union_name ILIKE '%ibew%'
          OR latest_union_name ILIKE '%electrical worker%'
          OR latest_union_name ILIKE '%international brotherhood of electrical%' THEN 'IBEW'

        -- Steelworkers
        WHEN latest_union_name ILIKE '%usw%'
          OR latest_union_name ILIKE '%steelworker%'
          OR latest_union_name ILIKE '%united steel%' THEN 'USW (Steelworkers)'

        -- Laborers
        WHEN latest_union_name ILIKE '%liuna%'
          OR latest_union_name ILIKE '%laborers%international%'
          OR latest_union_name ILIKE '%laborers%district%' THEN 'LIUNA (Laborers)'

        -- Operating Engineers
        WHEN latest_union_name ILIKE '%iuoe%'
          OR latest_union_name ILIKE '%operating engineer%' THEN 'IUOE (Operating Engineers)'

        -- CWA
        WHEN latest_union_name ILIKE '%cwa%'
          OR latest_union_name ILIKE '%communication%worker%' THEN 'CWA'

        -- UNITE HERE
        WHEN latest_union_name ILIKE '%unite here%'
          OR latest_union_name ILIKE '%local joint executive board%' THEN 'UNITE HERE'

        -- IATSE
        WHEN latest_union_name ILIKE '%iatse%'
          OR latest_union_name ILIKE '%theatrical stage employee%'
          OR latest_union_name ILIKE '%international alliance of theatrical%' THEN 'IATSE'

        -- SAG-AFTRA
        WHEN latest_union_name ILIKE '%sag-aftra%'
          OR latest_union_name ILIKE '%screen actor%'
          OR latest_union_name ILIKE '%sag %'
          OR latest_union_name ILIKE '%aftra%'
          OR latest_union_name ILIKE '% sag%'
          OR latest_union_name ILIKE 'sag-%' THEN 'SAG-AFTRA'

        -- Machinists
        WHEN latest_union_name ILIKE '%machinist%'
          OR latest_union_name ILIKE '%iam%'
          OR latest_union_name ILIKE '%iamaw%' THEN 'IAM (Machinists)'

        -- Nurses
        WHEN latest_union_name ILIKE '%nurse%'
          OR latest_union_name ILIKE '%nnu%'
          OR latest_union_name ILIKE '%unac%' THEN 'Nurses (NNU/State)'

        -- Longshoremen ILA
        WHEN latest_union_name ILIKE '%longshoremen%association%'
          OR latest_union_name ILIKE '%ila-%'
          OR latest_union_name ILIKE '%ila %' THEN 'ILA (Longshoremen)'

        -- Pipefitters/Plumbers (UA)
        WHEN latest_union_name ILIKE '%ppf%'
          OR latest_union_name ILIKE '%pipefitter%'
          OR latest_union_name ILIKE '%plumber%'
          OR latest_union_name ILIKE '%united association%journeymen%' THEN 'UA (Plumbers/Pipefitters)'

        -- Sheet Metal (SMART)
        WHEN latest_union_name ILIKE '%sheet metal%'
          OR latest_union_name ILIKE '%smart%' THEN 'SMART (Sheet Metal)'

        -- Bricklayers
        WHEN latest_union_name ILIKE '%bricklayer%'
          OR latest_union_name ILIKE '%bac-%'
          OR latest_union_name ILIKE '%bac %'
          OR latest_union_name ILIKE '% bac%' THEN 'BAC (Bricklayers)'

        -- Painters
        WHEN latest_union_name ILIKE '%painter%'
          OR latest_union_name ILIKE '%iupat%'
          OR latest_union_name ILIKE '%glazier%' THEN 'IUPAT (Painters)'

        -- Transit
        WHEN latest_union_name ILIKE '%atu%'
          OR latest_union_name ILIKE '%transit union%'
          OR latest_union_name ILIKE '%amalgamated transit%' THEN 'ATU (Transit)'

        -- ILWU
        WHEN latest_union_name ILIKE '%ilwu%'
          OR latest_union_name ILIKE '%longshore%warehouse%' THEN 'ILWU'

        -- Bakery
        WHEN latest_union_name ILIKE '%bctgm%'
          OR latest_union_name ILIKE '%bakery%' THEN 'BCTGM'

        -- RWDSU
        WHEN latest_union_name ILIKE '%rwdsu%'
          OR latest_union_name ILIKE '%retail%wholesale%' THEN 'RWDSU'

        -- OPEIU
        WHEN latest_union_name ILIKE '%opeiu%'
          OR latest_union_name ILIKE '%office%professional%' THEN 'OPEIU'

        -- Musicians
        WHEN latest_union_name ILIKE '%afm%'
          OR latest_union_name ILIKE '%musician%' THEN 'AFM (Musicians)'

        -- TWU
        WHEN latest_union_name ILIKE '%twu%'
          OR latest_union_name ILIKE '%transport worker%' THEN 'TWU'

        -- UE
        WHEN latest_union_name ILIKE '% ue %'
          OR latest_union_name ILIKE '%electrical, radio%'
          OR latest_union_name ILIKE 'ue-%' THEN 'UE'

        -- Mine Workers
        WHEN latest_union_name ILIKE '%umw%'
          OR latest_union_name ILIKE '%mine worker%' THEN 'UMWA'

        -- Ironworkers
        WHEN latest_union_name ILIKE '%ironworker%'
          OR latest_union_name ILIKE '%bridge, structural%'
          OR latest_union_name ILIKE '%bsoiw%' THEN 'Ironworkers'

        -- Roofers
        WHEN latest_union_name ILIKE '%roofer%'
          OR latest_union_name ILIKE '%rwaw%' THEN 'Roofers'

        -- Boilermakers
        WHEN latest_union_name ILIKE '%boilermaker%' THEN 'Boilermakers'

        -- Directors Guild
        WHEN latest_union_name ILIKE '%directors guild%'
          OR latest_union_name ILIKE '%dga%' THEN 'DGA'

        -- Writers Guild
        WHEN latest_union_name ILIKE '%writers guild%'
          OR latest_union_name ILIKE '%wga%' THEN 'WGA'

        -- Elevator Constructors
        WHEN latest_union_name ILIKE '%elevator%'
          OR latest_union_name ILIKE '%iuec%' THEN 'IUEC (Elevator)'

        -- Insulators
        WHEN latest_union_name ILIKE '%insulator%'
          OR latest_union_name ILIKE '%heat%frost%' THEN 'Insulators'

        -- TCU
        WHEN latest_union_name ILIKE '%transportation communication%'
          OR latest_union_name ILIKE '%tcu%' THEN 'TCU'

        -- PUBLIC SECTOR (to exclude)
        WHEN latest_union_name ILIKE '%afge%'
          OR latest_union_name ILIKE '%government employee%'
          OR latest_union_name ILIKE '%apwu%'
          OR latest_union_name ILIKE '%postal worker%'
          OR latest_union_name ILIKE '%afscme%'
          OR latest_union_name ILIKE '%state%county%municipal%'
          OR latest_union_name ILIKE '%teacher%'
          OR latest_union_name ILIKE '%aft %'
          OR latest_union_name ILIKE '%nea %'
          OR latest_union_name ILIKE '%firefighter%'
          OR latest_union_name ILIKE '%iaff%'
          OR latest_union_name ILIKE '%police%' THEN 'PUBLIC SECTOR'

        -- AFL-CIO generic
        WHEN latest_union_name ILIKE '%afl-cio%'
          OR latest_union_name ILIKE '%afl cio%'
          OR latest_union_name ILIKE '%area trades council%' THEN 'AFL-CIO (Generic)'

        ELSE 'UNCLASSIFIED'
    END
'''

# Sheet 1: Coverage by Union Affiliation
cur.execute(f'''
    WITH classified AS (
        SELECT
            {CLASSIFICATION_SQL} as union_affiliation,
            employer_id,
            employer_name,
            latest_unit_size,
            latest_union_name,
            city,
            state
        FROM f7_employers
        WHERE latest_unit_size IS NOT NULL
          AND latest_unit_size > 0
          AND latest_unit_size < 500000
          AND employer_name NOT ILIKE '%postal%'
          AND employer_name NOT ILIKE '%department of%'
          AND employer_name NOT ILIKE '%federal%'
          AND employer_name NOT ILIKE '%state of %'
          AND employer_name NOT ILIKE '%city of %'
          AND employer_name NOT ILIKE '%county of %'
          AND employer_name NOT ILIKE '%school%'
          AND employer_name NOT ILIKE '%HUD/%'
    )
    SELECT
        union_affiliation,
        COUNT(*) as employer_count,
        PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size)::int as median_unit_size,
        AVG(latest_unit_size)::int as avg_unit_size,
        SUM(latest_unit_size) as raw_sum,
        (COUNT(*) * PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY latest_unit_size))::bigint as estimated_workers,
        MAX(latest_unit_size) as max_unit_size
    FROM classified
    WHERE union_affiliation != 'PUBLIC SECTOR'
    GROUP BY union_affiliation
    ORDER BY estimated_workers DESC
''')

df_summary = pd.DataFrame(cur.fetchall())
df_summary.columns = ['Union Affiliation', 'Employer Count', 'Median Unit Size', 'Avg Unit Size', 'Raw Sum', 'Estimated Workers', 'Max Unit Size']

# Sheet 2: Remaining unclassified union names
cur.execute(f'''
    WITH classified AS (
        SELECT
            {CLASSIFICATION_SQL} as union_affiliation,
            latest_union_name,
            latest_unit_size
        FROM f7_employers
        WHERE latest_unit_size > 0
          AND latest_unit_size < 500000
          AND employer_name NOT ILIKE '%postal%'
          AND employer_name NOT ILIKE '%department of%'
          AND employer_name NOT ILIKE '%federal%'
          AND employer_name NOT ILIKE '%state of %'
          AND employer_name NOT ILIKE '%city of %'
          AND employer_name NOT ILIKE '%county of %'
          AND employer_name NOT ILIKE '%school%'
    )
    SELECT
        latest_union_name,
        COUNT(*) as employer_count,
        SUM(latest_unit_size) as total_workers,
        AVG(latest_unit_size)::int as avg_size,
        MAX(latest_unit_size) as max_size
    FROM classified
    WHERE union_affiliation = 'UNCLASSIFIED'
    GROUP BY latest_union_name
    ORDER BY total_workers DESC
    LIMIT 500
''')

df_unclassified = pd.DataFrame(cur.fetchall())
df_unclassified.columns = ['Union Name', 'Employer Count', 'Total Workers (Raw)', 'Avg Unit Size', 'Max Unit Size']

# Sheet 3: VR Data Summary
cur.execute('''
    SELECT
        COALESCE(extracted_affiliation, 'Unknown') as affiliation,
        COUNT(*) as case_count,
        SUM(COALESCE(num_employees, 0)) as total_workers,
        AVG(num_employees)::int as avg_size
    FROM nlrb_voluntary_recognition
    GROUP BY extracted_affiliation
    ORDER BY total_workers DESC
''')

df_vr = pd.DataFrame(cur.fetchall())
df_vr.columns = ['Union Affiliation', 'VR Cases', 'Workers Organized', 'Avg Unit Size']

# Sheet 4: Platform totals
total_employers = df_summary['Employer Count'].sum()
total_est_workers = df_summary['Estimated Workers'].sum()
vr_workers = df_vr['Workers Organized'].sum()
platform_total = total_est_workers + vr_workers
bls = 7300000

classified_df = df_summary[~df_summary['Union Affiliation'].isin(['UNCLASSIFIED', 'AFL-CIO (Generic)'])]
unclassified_df = df_summary[df_summary['Union Affiliation'].isin(['UNCLASSIFIED', 'AFL-CIO (Generic)'])]

totals = {
    'Metric': [
        'F7 Private Employers',
        'F7 Estimated Workers (employers x median)',
        'F7 Raw Sum (with duplication)',
        'VR Cases',
        'VR Workers',
        'Total Platform Coverage',
        'BLS Private Sector Benchmark',
        'Coverage Rate',
        '',
        'Classified Employers',
        'Unclassified/Generic Employers',
        'Classified Est. Workers',
        'Unclassified/Generic Est. Workers',
        'Classification Rate'
    ],
    'Value': [
        total_employers,
        total_est_workers,
        df_summary['Raw Sum'].sum(),
        df_vr['VR Cases'].sum(),
        vr_workers,
        platform_total,
        bls,
        f"{platform_total / bls * 100:.1f}%",
        '',
        classified_df['Employer Count'].sum(),
        unclassified_df['Employer Count'].sum(),
        classified_df['Estimated Workers'].sum(),
        unclassified_df['Estimated Workers'].sum(),
        f"{classified_df['Employer Count'].sum() / total_employers * 100:.1f}%"
    ]
}
df_totals = pd.DataFrame(totals)

# Write to Excel
with pd.ExcelWriter('private_sector_coverage_v2.xlsx', engine='openpyxl') as writer:
    df_summary.to_excel(writer, sheet_name='Coverage by Union', index=False)
    df_unclassified.to_excel(writer, sheet_name='Unclassified Unions', index=False)
    df_vr.to_excel(writer, sheet_name='VR Data', index=False)
    df_totals.to_excel(writer, sheet_name='Platform Totals', index=False)

    # Auto-adjust column widths
    for sheet_name in writer.sheets:
        worksheet = writer.sheets[sheet_name]
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 60)
            worksheet.column_dimensions[column_letter].width = adjusted_width

print('=' * 60)
print('Excel file created: private_sector_coverage_v2.xlsx')
print('=' * 60)
print()
print('SUMMARY:')
print(f'  Total private employers:   {total_employers:>10,}')
print(f'  Estimated workers:         {total_est_workers:>10,}')
print(f'  + VR workers:              {vr_workers:>10,}')
print(f'  Platform total:            {platform_total:>10,}')
print(f'  BLS benchmark:             {bls:>10,}')
print(f'  Coverage rate:             {platform_total/bls*100:>9.1f}%')
print()
print(f'  Classified employers:      {classified_df["Employer Count"].sum():>10,} ({classified_df["Employer Count"].sum()/total_employers*100:.1f}%)')
print(f'  Unclassified employers:    {unclassified_df["Employer Count"].sum():>10,} ({unclassified_df["Employer Count"].sum()/total_employers*100:.1f}%)')
print()
print('TOP UNIONS BY ESTIMATED WORKERS:')
for _, row in df_summary.head(15).iterrows():
    print(f"  {row['Union Affiliation']:<30} {row['Estimated Workers']:>10,}")

conn.close()
