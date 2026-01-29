import psycopg2
import pandas as pd
import re

conn = psycopg2.connect(
    host='localhost', 
    port=5432, 
    database='olms_multiyear', 
    user='postgres', 
    password='Juniordog33!'
)

# Load F7-only unions
f7_only = pd.read_csv(r"C:\Users\jakew\Downloads\Claude Ai union project\lm and f7 documents 1_22\f7_only_multiyear_check.csv")

# Get the 37 that have 2010 LM filings
f7_fnums = f7_only['f_num'].tolist()
f7_fnums_str = ','.join([f"'{x}'" for x in f7_fnums])

has_lm = pd.read_sql(f"""
    SELECT f_num, union_name, aff_abbr, 
           MAX(yr_covered) as last_lm_year, 
           MIN(yr_covered) as first_lm_year,
           MAX(members) as max_members
    FROM lm_data 
    WHERE f_num IN ({f7_fnums_str})
    GROUP BY f_num, union_name, aff_abbr
    ORDER BY f_num
""", conn)

# Merge with F7 data
f7_only['f_num_str'] = f7_only['f_num'].astype(str)
has_lm['f_num_str'] = has_lm['f_num'].astype(str)

matched = f7_only.merge(has_lm, on='f_num_str', how='inner', suffixes=('_f7', '_lm'))

print("="*120)
print("F7 UNIONS WITH LM MATCH - LIKELY DEFUNCT (last LM filing 2010)")  
print("="*120)
print(f"\nFound {len(matched)} F7 unions that DO have LM filings\n")

# Sort by workers
matched_sorted = matched.sort_values('total_workers', ascending=False)
print(matched_sorted[['f_num_str', 'union_name_f7', 'employer_count', 'total_workers', 'union_name_lm', 'aff_abbr', 'last_lm_year', 'max_members']].to_string())

# Sum stats
print(f"\n\nSUMMARY OF MATCHED F7-LM UNIONS:")
print(f"  Total unions: {len(matched)}")
print(f"  Total F7 employers: {matched['employer_count'].sum()}")
print(f"  Total F7 workers: {matched['total_workers'].sum():,}")
print(f"  All last filed LM in: {matched['last_lm_year'].unique()}")

# Now look at truly unmatched
matched_fnums = set(matched['f_num_str'].astype(int))
truly_unmatched_fnums = set(f7_only['f_num']) - matched_fnums
truly_unmatched = f7_only[f7_only['f_num'].isin(truly_unmatched_fnums)].copy()

print(f"\n\n" + "="*120)
print("TRULY UNMATCHED - NO LM FILING EXISTS FOR THIS FILE NUMBER")
print("="*120)
print(f"\n{len(truly_unmatched)} unions have F7 records but NO LM filing at all\n")

# Try to match these by name/local to existing LM unions
def extract_local_aff(name):
    if pd.isna(name):
        return None, None
    name = str(name).upper()
    
    # Extract local number
    local = None
    patterns = [
        r'-(\d+[A-Z]?(?:-[A-Z0-9]+)?)\s*$',
        r'LOCAL\s*#?\s*(\d+[A-Z]?)',
        r'\s(\d+[A-Z]?)$',
    ]
    for p in patterns:
        m = re.search(p, name)
        if m:
            local = re.sub(r'[^0-9]', '', m.group(1))
            if local:
                break
    
    # Extract affiliation
    aff_map = [
        (r'\bIBT\b|TEAMSTER', 'IBT'),
        (r'\bSEIU\b|SERVICE EMPLOYEES', 'SEIU'),
        (r'\bUAW\b|AUTO.*WORKERS', 'UAW'),
        (r'\bUSW\b|STEELWORKERS|UNITED STEEL', 'USW'),
        (r'\bCWA\b|COMMUNICATIONS WORKERS', 'CWA'),
        (r'\bUFCW\b|FOOD.*COMMERCIAL', 'UFCW'),
        (r'\bLIUNA\b|\bLABORERS\b', 'LIUNA'),
        (r'\bIUOE\b|OPERATING ENGINEERS', 'IUOE'),
        (r'\bIBEW\b|ELECTRICAL WORKERS', 'IBEW'),
        (r'\bAFSCME\b', 'AFSCME'),
        (r'\bIAMAW?\b|MACHINISTS', 'IAM'),
        (r'\bGCC\b|GRAPHIC', 'GCC'),
        (r'\bGMPI?U?\b|GLASS.*MOLDERS', 'GMP'),
        (r'\bRWDSU\b', 'RWDSU'),
        (r'\bATU\b|TRANSIT UNION', 'ATU'),
        (r'\bUMWA\b|MINE WORKERS', 'UMWA'),
        (r'\bAFGE\b', 'AFGE'),
        (r'\bIATSE\b|THEATRICAL', 'IATSE'),
        (r'\bUWUA\b|UTILITY WORKERS', 'UWUA'),
        (r'\bSPFPA\b', 'SPFPA'),
        (r'\bWU\b|WORKERS UNITED', 'WU'),
    ]
    aff = None
    for pattern, aff_name in aff_map:
        if re.search(pattern, name):
            aff = aff_name
            break
    return local, aff

truly_unmatched['local_num'], truly_unmatched['affiliation'] = zip(*truly_unmatched['union_name'].apply(extract_local_aff))

# Get LM unions for matching
lm_all = pd.read_sql("""
    SELECT f_num, union_name, aff_abbr, MAX(members) as members, MAX(yr_covered) as last_year
    FROM lm_data
    GROUP BY f_num, union_name, aff_abbr
""", conn)
lm_all['local_num'], lm_all['aff_parsed'] = zip(*lm_all['union_name'].apply(extract_local_aff))

# Try to find matches
name_matches = []
for idx, f7 in truly_unmatched.iterrows():
    f7_local = f7['local_num']
    f7_aff = f7['affiliation']
    
    if f7_local and f7_aff and len(f7_local) >= 2:
        # Find LM with same aff + local
        candidates = lm_all[
            (lm_all['local_num'] == f7_local) &
            ((lm_all['aff_abbr'] == f7_aff) | (lm_all['aff_parsed'] == f7_aff))
        ]
        if len(candidates) > 0:
            best = candidates.loc[candidates['members'].idxmax()]
            name_matches.append({
                'f7_fnum': f7['f_num'],
                'f7_name': f7['union_name'],
                'f7_workers': f7['total_workers'],
                'f7_employers': f7['employer_count'],
                'lm_fnum': best['f_num'],
                'lm_name': best['union_name'],
                'lm_members': best['members'],
                'match_type': 'LOCAL_AFF_INFERRED'
            })

name_matches_df = pd.DataFrame(name_matches)
print(f"\nPOTENTIAL MATCHES BY LOCAL NUMBER + AFFILIATION: {len(name_matches_df)}")
if len(name_matches_df) > 0:
    print(name_matches_df.sort_values('f7_workers', ascending=False).to_string())

# Final summary
still_unmatched_fnums = set(truly_unmatched['f_num']) - set(name_matches_df.get('f7_fnum', []))
still_unmatched = truly_unmatched[truly_unmatched['f_num'].isin(still_unmatched_fnums)]

print(f"\n\n" + "="*120)
print("FINAL SUMMARY")
print("="*120)
print(f"\nOriginal F7-only unions: 167")
print(f"  - Have LM filing (2010 only, likely defunct): {len(matched)} ({100*len(matched)/167:.1f}%)")
print(f"  - Matched by local+aff to different f_num: {len(name_matches_df)} ({100*len(name_matches_df)/167:.1f}%)")
print(f"  - Truly unmatched: {len(still_unmatched)} ({100*len(still_unmatched)/167:.1f}%)")

print(f"\n\nTRULY UNMATCHED TOP 25 (by workers):")
print(still_unmatched.nlargest(25, 'total_workers')[['f_num', 'union_name', 'employer_count', 'total_workers', 'local_num', 'affiliation']].to_string())

# Save comprehensive report
matched.to_csv(r"C:\Users\jakew\Downloads\f7_matched_defunct_lm.csv", index=False)
truly_unmatched.to_csv(r"C:\Users\jakew\Downloads\f7_truly_unmatched.csv", index=False)
if len(name_matches_df) > 0:
    name_matches_df.to_csv(r"C:\Users\jakew\Downloads\f7_inferred_matches.csv", index=False)

print("\n\nSaved reports to Downloads folder")

conn.close()
