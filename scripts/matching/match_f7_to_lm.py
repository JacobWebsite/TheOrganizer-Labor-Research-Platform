import os
import psycopg2
import pandas as pd
import re

# Connect to database
conn = psycopg2.connect(
    host='localhost', 
    port=5432, 
    database='olms_multiyear', 
    user='postgres', 
    password='os.environ.get('DB_PASSWORD', '')'
)

# Load F7-only unions from CSV
f7_only = pd.read_csv(r"C:\Users\jakew\Downloads\Claude Ai union project\lm and f7 documents 1_22\f7_only_multiyear_check.csv")
print(f"Loaded {len(f7_only)} F7-only unions")

# Load LM unions from database
lm_unions = pd.read_sql("""
    SELECT DISTINCT f_num, union_name, aff_abbr 
    FROM lm_data 
    WHERE yr_covered >= 2015
""", conn)
print(f"Loaded {len(lm_unions)} LM unions (2015+)")

# Function to extract local number from union name
def extract_local_number(name):
    if pd.isna(name):
        return None
    name = str(name).upper()
    # Try various patterns
    patterns = [
        r'LOCAL\s*#?\s*(\d+)',
        r'-(\d+)$',
        r'-(\d+)\s',
        r'\s(\d+)$',
        r'LU\s*(\d+)',
        r'L\.?U\.?\s*(\d+)',
    ]
    for p in patterns:
        match = re.search(p, name)
        if match:
            return match.group(1)
    return None

# Function to extract affiliation from union name
def extract_affiliation(name):
    if pd.isna(name):
        return None
    name = str(name).upper()
    affiliations = {
        'IBT': ['IBT', 'TEAMSTER', 'BROTHERHOOD OF TEAMSTERS'],
        'SEIU': ['SEIU', 'SERVICE EMPLOYEES'],
        'UAW': ['UAW', 'AUTO WORKERS', 'AUTOMOBILE'],
        'USW': ['USW', 'STEELWORKERS', 'UNITED STEEL'],
        'CWA': ['CWA', 'COMMUNICATIONS WORKERS'],
        'UFCW': ['UFCW', 'FOOD.*COMMERCIAL'],
        'LIUNA': ['LIUNA', 'LABORERS'],
        'IUOE': ['IUOE', 'OPERATING ENGINEERS'],
        'IBEW': ['IBEW', 'ELECTRICAL WORKERS'],
        'AFSCME': ['AFSCME', 'STATE.*COUNTY.*MUNICIPAL'],
        'IAM': ['IAM', 'IAMAW', 'MACHINISTS'],
        'GCC': ['GCC', 'GRAPHIC COMMUNICATIONS'],
        'RWDSU': ['RWDSU', 'RETAIL.*WHOLESALE'],
        'UNITE HERE': ['UNITE HERE'],
        'ATU': ['ATU', 'TRANSIT UNION'],
        'UMWA': ['UMWA', 'MINE WORKERS'],
        'AFGE': ['AFGE', 'GOVERNMENT EMPLOYEES'],
        'IATSE': ['IATSE', 'THEATRICAL'],
    }
    for aff, patterns in affiliations.items():
        for p in patterns:
            if re.search(p, name):
                return aff
    return None

# Process F7-only unions
f7_only['local_num'] = f7_only['union_name'].apply(extract_local_number)
f7_only['affiliation'] = f7_only['union_name'].apply(extract_affiliation)

# Process LM unions  
lm_unions['local_num'] = lm_unions['union_name'].apply(extract_local_number)
lm_unions['affiliation_parsed'] = lm_unions['union_name'].apply(extract_affiliation)

print("\nF7-only affiliations found:")
print(f7_only['affiliation'].value_counts())

# Try to match
matches = []
for idx, f7 in f7_only.iterrows():
    f7_local = f7['local_num']
    f7_aff = f7['affiliation']
    
    if f7_local and f7_aff:
        # Look for match in LM by affiliation + local number
        potential = lm_unions[
            (lm_unions['local_num'] == f7_local) & 
            ((lm_unions['aff_abbr'] == f7_aff) | (lm_unions['affiliation_parsed'] == f7_aff))
        ]
        
        if len(potential) > 0:
            for _, lm in potential.iterrows():
                matches.append({
                    'f7_fnum': f7['f_num'],
                    'f7_name': f7['union_name'],
                    'f7_employers': f7['employer_count'],
                    'f7_workers': f7['total_workers'],
                    'lm_fnum': lm['f_num'],
                    'lm_name': lm['union_name'],
                    'match_type': 'EXACT_LOCAL_AFF'
                })
        else:
            # Try just local number match within same affiliation family
            potential2 = lm_unions[lm_unions['local_num'] == f7_local]
            if len(potential2) > 0 and len(potential2) < 10:  # Avoid too many false positives
                for _, lm in potential2.iterrows():
                    matches.append({
                        'f7_fnum': f7['f_num'],
                        'f7_name': f7['union_name'],
                        'f7_employers': f7['employer_count'],
                        'f7_workers': f7['total_workers'],
                        'lm_fnum': lm['f_num'],
                        'lm_name': lm['union_name'],
                        'match_type': 'LOCAL_NUM_ONLY'
                    })

matches_df = pd.DataFrame(matches)
print(f"\n=== FOUND {len(matches_df)} POTENTIAL MATCHES ===\n")

if len(matches_df) > 0:
    # Show exact matches first
    exact = matches_df[matches_df['match_type'] == 'EXACT_LOCAL_AFF']
    print(f"EXACT MATCHES (affiliation + local number): {len(exact)}")
    print(exact[['f7_fnum', 'f7_name', 'f7_workers', 'lm_fnum', 'lm_name']].to_string())
    
    print("\n" + "="*80 + "\n")
    
    # Show local-only matches
    local_only = matches_df[matches_df['match_type'] == 'LOCAL_NUM_ONLY']
    print(f"LOCAL NUMBER MATCHES (different affiliation): {len(local_only)}")
    if len(local_only) > 0:
        print(local_only[['f7_fnum', 'f7_name', 'f7_workers', 'lm_fnum', 'lm_name']].head(30).to_string())

# Save results
matches_df.to_csv(r"C:\Users\jakew\Downloads\f7_to_lm_matches.csv", index=False)
print(f"\nSaved matches to f7_to_lm_matches.csv")

conn.close()
